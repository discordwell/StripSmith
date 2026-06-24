"""Image generation using DALL-E 3 (Stage 2 & 4)."""

import os
import re
import time
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional
from openai import OpenAI

from src.utils.logger import get_logger
from src.utils.config import get_config

logger = get_logger("stripsmith.generator")


class ImageGenerator:
    """Generate images using DALL-E 3 API."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize image generator.

        Args:
            api_key: OpenAI API key (uses OPENAI_API_KEY env var if None)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")

        self.client = OpenAI(api_key=self.api_key)
        self.config = get_config()

        self.total_cost = 0.0

        logger.info("Image generator initialized")

    def generate_image(
        self,
        prompt: str,
        output_path: str,
        size: str = None,
        quality: str = None,
        style: str = None
    ) -> Dict[str, Any]:
        """
        Generate a single image using DALL-E 3.

        Args:
            prompt: Image generation prompt
            output_path: Path to save the image
            size: Image size (1024x1024, 1024x1792, 1792x1024)
            quality: Image quality (standard or hd)
            style: Image style (natural or vivid)

        Returns:
            Dict with image path, URL, and cost
        """
        # Use config defaults if not specified
        size = size or self.config.get("image.size", "1024x1024")
        quality = quality or self.config.get("image.quality", "standard")
        style = style or self.config.get("image.style", "natural")

        logger.info(f"Generating image: {prompt[:60]}...")
        logger.debug(f"Size: {size}, Quality: {quality}, Style: {style}")

        try:
            # Call DALL-E 3 API
            response = self.client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size=size,
                quality=quality,
                style=style,
                n=1
            )

            # Get image URL
            image_url = response.data[0].url

            # Download image
            self._download_image(image_url, output_path)

            # Calculate cost
            cost = self._calculate_cost(size, quality)
            self.total_cost += cost

            logger.info(f"Image generated: {output_path} (${cost:.3f})")

            return {
                "path": output_path,
                "url": image_url,
                "cost": cost,
                "size": size,
                "quality": quality
            }

        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            raise

    def generate_character_sheet(
        self,
        character_name: str,
        prompts: List[Dict[str, str]],
        output_dir: str
    ) -> List[Dict[str, Any]]:
        """
        Generate character reference sheet images.

        Args:
            character_name: Character name
            prompts: List of prompt dicts from CharacterTemplateManager
            output_dir: Directory to save images

        Returns:
            List of generated image info
        """
        logger.info(f"Generating character sheet for {character_name}...")

        # Create output directory
        safe_name = self._sanitize_filename(character_name)
        char_dir = Path(output_dir) / safe_name
        char_dir.mkdir(parents=True, exist_ok=True)

        generated = []

        for i, prompt_data in enumerate(prompts):
            angle = prompt_data["angle"]
            prompt = prompt_data["prompt"]

            # Build a flat, separator-free filename. Both parts must be
            # sanitized: the default angle "3/4" would otherwise make this
            # "{name}_3/4.png", which the filesystem reads as a nested
            # "{name}_3/" directory holding "4.png" (see _sanitize_filename),
            # scattering the reference sheet. The name is sanitized too so the
            # filename matches its (already-sanitized) directory.
            filename = f"{safe_name}_{self._sanitize_filename(angle)}.png"
            output_path = str(char_dir / filename)

            try:
                # Generate image
                result = self.generate_image(prompt, output_path)
                result["angle"] = angle
                result["character"] = character_name

                generated.append(result)

                # Rate limiting
                if i < len(prompts) - 1:
                    time.sleep(1)  # Be nice to the API

            except Exception as e:
                logger.error(f"Failed to generate {character_name} {angle}: {e}")
                continue

        logger.info(f"Generated {len(generated)}/{len(prompts)} images for {character_name}")

        return generated

    def generate_panel(
        self,
        panel_data: Dict,
        character_prompts: Dict[str, str],
        output_path: str,
        style: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a comic panel image.

        Args:
            panel_data: Panel data from panel breakdown
            character_prompts: Dict mapping character names to base prompts
            output_path: Path to save panel image
            style: Project art style (e.g. "noir comic"). Applied as the panel's
                overall art direction so backgrounds match the characters. Falls
                back to the panel's own ``style`` then a generic default.

        Returns:
            Generated image info
        """
        # Build panel prompt
        prompt = self._build_panel_prompt(panel_data, character_prompts, style)

        logger.info(f"Generating panel {panel_data.get('panel_num', '?')}: {panel_data.get('description', '')[:50]}...")

        # Generate image
        result = self.generate_image(prompt, output_path)
        result["panel_num"] = panel_data.get("panel_num")
        result["description"] = panel_data.get("description")

        return result

    def _build_panel_prompt(
        self,
        panel_data: Dict,
        character_prompts: Dict[str, str],
        style: Optional[str] = None
    ) -> str:
        """Build complete prompt for a comic panel."""

        # Base description
        description = panel_data.get("description", "")

        # Add character prompts
        characters = panel_data.get("characters", [])
        if characters and character_prompts:
            char_descriptions = []
            for char_name in characters:
                if char_name in character_prompts:
                    char_descriptions.append(character_prompts[char_name])

            if char_descriptions:
                description += f". Characters: {', '.join(char_descriptions)}"

        # Add camera angle
        camera = panel_data.get("camera_angle", "medium-shot")
        description += f", {camera}"

        # Add style. Prefer the explicit project art style passed by the caller
        # so every panel (backgrounds included) matches the comic's look; the
        # breakdown's panel dicts carry no "style" key, so without this the whole
        # comic would silently fall back to the generic default below.
        style = style or panel_data.get("style") or "comic book art"
        prompt = f"{style}, {description}"

        # Clean up
        prompt = " ".join(prompt.split())

        # Sanitize for content policy
        prompt = self._sanitize_prompt(prompt)

        return prompt

    def _sanitize_prompt(self, prompt: str) -> str:
        """
        Sanitize prompt to avoid DALL-E 3 content policy violations.

        Replaces explicit violence, death, weapons with safer alternatives.
        """
        # Matching is case-insensitive via re.IGNORECASE below; keep original case.
        sanitized = prompt

        # Replace problematic terms with safe alternatives
        replacements = {
            # Dead bodies / violence
            r'\bcovered body\b': 'covered figure on the ground',
            r'\bdead body\b': 'figure on the ground',
            r'\bcorpse\b': 'figure',
            r'\bbody\b': 'scene',
            r'\bpulling back the sheet\b': 'examining the scene',
            r'\bexamines the body\b': 'examines the scene',
            r'\bexamining the body\b': 'examining the scene',

            # Blood / gore
            r'\bblood\b': 'dark stains',
            r'\bbleeding\b': 'injured',
            r'\bwounded\b': 'hurt',
            r'\bgore\b': '',

            # Weapons in threatening contexts
            r'\bpointing (?:a )?gun\b': 'holding weapon at side',
            r'\baiming (?:a )?gun\b': 'holding weapon',
            r'\bfiring (?:a )?gun\b': 'in action',
            r'\bshooting\b': 'in conflict',
            r'\bwielding (?:a )?weapon\b': 'holding weapon',

            # Violence
            r'\bkilling\b': 'confronting',
            r'\bmurder\b': 'crime',
            r'\battacking\b': 'confronting',
            r'\bstabbing\b': 'in conflict',
            r'\bbeating\b': 'fighting',
        }

        for pattern, replacement in replacements.items():
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

        # Clean up double spaces
        sanitized = " ".join(sanitized.split())

        logger.debug(f"Sanitized prompt: {sanitized}")

        return sanitized

    def _download_image(self, url: str, output_path: str):
        """Download image from URL to file."""
        try:
            # Create parent directory
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            # Download image
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            # Save to file
            with open(output_path, 'wb') as f:
                f.write(response.content)

        except Exception as e:
            logger.error(f"Failed to download image: {e}")
            raise

    def _calculate_cost(self, size: str, quality: str) -> float:
        """Calculate cost for DALL-E 3 generation."""
        # DALL-E 3 pricing
        costs = {
            "1024x1024": {"standard": 0.040, "hd": 0.080},
            "1024x1792": {"standard": 0.080, "hd": 0.120},
            "1792x1024": {"standard": 0.080, "hd": 0.120}
        }

        return costs.get(size, {}).get(quality, 0.040)

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a string into one safe path component.

        Disallowed characters are mapped to ``-`` (whitespace to ``_``) rather
        than dropped. That distinction matters for values like the default
        ``"3/4"`` camera angle: dropping the slash *or* leaving it both look
        harmless until ``f"{name}_{angle}.png"`` becomes ``"Sarah_3/4.png"``,
        which the filesystem reads as a nested ``Sarah_3/`` directory holding
        ``4.png`` instead of one flat file. Mapping the slash to ``-`` keeps the
        result a single separator-free component. Unicode letters and digits
        (e.g. accented names) are preserved, since ``str.isalnum`` is
        Unicode-aware.
        """
        cleaned = "".join(
            c if (c.isalnum() or c in ("-", "_"))
            else ("_" if c.isspace() else "-")
            for c in name
        )
        # Collapse runs of separators and trim leading/trailing ones so we never
        # emit "" (which would write straight into the parent directory).
        cleaned = re.sub(r"[-_]{2,}", "_", cleaned).strip("-_")
        return cleaned or "unnamed"

    def get_total_cost(self) -> float:
        """Get total cost of all generations."""
        return self.total_cost

    def reset_cost_tracking(self):
        """Reset cost tracking."""
        self.total_cost = 0.0
        logger.info("Cost tracking reset")
