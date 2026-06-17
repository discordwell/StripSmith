"""Chapter to panel breakdown using Claude (Stage 3)."""

import json
import os
from typing import Dict, List, Optional
from anthropic import Anthropic

from src.utils.logger import get_logger
from src.utils.config import get_config, DEFAULT_LLM_MODEL, DEFAULT_LLM_MAX_TOKENS

logger = get_logger("stripsmith.breakdown")


class PanelBreakdown:
    """Break chapters into comic panels with dialogue and layout."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize panel breakdown.

        Args:
            api_key: Anthropic API key
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment")

        self.client = Anthropic(api_key=self.api_key)
        self.config = get_config()

        logger.info("Panel breakdown initialized")

    def breakdown_chapter(
        self,
        chapter: Dict,
        story_text: str,
        project_spec: Dict
    ) -> Dict:
        """
        Break down a chapter into panels.

        Args:
            chapter: Chapter data from project spec
            story_text: Full story text
            project_spec: Project specification with characters and style

        Returns:
            Panel breakdown with pages and panels
        """
        chapter_num = chapter["number"]
        logger.info(f"Breaking down chapter {chapter_num}...")

        # Extract chapter text
        chapter_text = self._extract_chapter_text(chapter, story_text)

        # Build breakdown prompt
        prompt = self._build_breakdown_prompt(chapter, chapter_text, project_spec)

        # Call Claude API
        try:
            response = self.client.messages.create(
                model=self.config.get("analysis.llm_model", DEFAULT_LLM_MODEL),
                max_tokens=self.config.get("analysis.max_output_tokens", DEFAULT_LLM_MAX_TOKENS),
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # Parse response. Pull the first text block rather than assuming
            # content[0] is text — keeps working if a thinking block is ever
            # returned ahead of the answer.
            result_text = next(
                (block.text for block in response.content if block.type == "text"),
                ""
            )
            panel_data = self._parse_response(result_text)

            # Add chapter info
            panel_data["chapter_number"] = chapter_num
            panel_data["chapter_title"] = chapter.get("title", f"Chapter {chapter_num}")

            logger.info(f"Chapter {chapter_num}: {len(panel_data['pages'])} pages, "
                       f"{sum(len(p['panels']) for p in panel_data['pages'])} panels")

            return panel_data

        except Exception as e:
            logger.error(f"Panel breakdown failed: {e}")
            raise

    def _extract_chapter_text(self, chapter: Dict, story_text: str) -> str:
        """Extract text for a specific chapter."""
        # Split story into paragraphs
        paragraphs = story_text.split('\n\n')

        # Get chapter paragraphs
        start = chapter.get("start_paragraph", 0)
        end = chapter.get("end_paragraph", len(paragraphs))

        chapter_paras = paragraphs[start:end]
        chapter_text = "\n\n".join(chapter_paras)

        return chapter_text

    def _build_breakdown_prompt(
        self,
        chapter: Dict,
        chapter_text: str,
        project_spec: Dict
    ) -> str:
        """Build the panel breakdown prompt."""

        characters = project_spec.get("characters", [])
        character_names = [c["name"] for c in characters]

        style = project_spec.get("style", {})
        art_style = style.get("art_style", "comic book")

        max_characters = self.config.get("characters.max_per_panel", 3)
        target_panels = self.config.get("panels.target_panels_per_page", 3)

        prompt = f"""Break down this chapter into comic book panels for visual storytelling.

Chapter: {chapter.get('title', '')}
Summary: {chapter.get('summary', '')}

Text:
{chapter_text}

Known Characters: {', '.join(character_names)}
Art Style: {art_style}

Please provide a JSON response with the following structure:

{{
  "pages": [
    {{
      "page_number": 1,
      "layout": "3-panel-grid",
      "panels": [
        {{
          "panel_num": 1,
          "description": "Visual description of what to draw (setting, action, characters, mood)",
          "dialogue": [
            {{
              "speaker": "Character Name",
              "text": "What they say",
              "emotion": "happy/sad/angry/neutral"
            }}
          ],
          "narration": "Optional narration text",
          "characters": ["Character1", "Character2"],
          "camera_angle": "close-up/medium-shot/long-shot",
          "environment": "location name if applicable",
          "key_moment": true/false
        }}
      ]
    }}
  ]
}}

Instructions:
- Aim for ~{target_panels} panels per page
- ONLY use characters from the Known Characters list
- Limit to {max_characters} characters per panel maximum
- Be VERY specific in visual descriptions (what we see, not what we feel)
- Separate dialogue from narration
- Indicate camera angles for cinematic flow
- Mark key dramatic moments with key_moment: true
- Choose layouts: "3-panel-grid", "4-panel-grid", "splash" (for dramatic moments), or "webtoon"
- For action scenes: more panels with varied angles
- For dialogue: fewer, larger panels
- Make sure EVERY line of dialogue and important action is captured

Visual Description Guidelines:
- Include: lighting, expressions, body language, background details
- Example: "Detective Sarah stands in the rain-soaked alley, her green eyes narrowed, hand on her holster. Neon signs reflect in puddles behind her."

Return ONLY the JSON, no additional text."""

        return prompt

    def _parse_response(self, response_text: str) -> Dict:
        """Parse Claude's JSON response."""
        try:
            # Extract JSON
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1

            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in response")

            json_text = response_text[json_start:json_end]
            panel_data = json.loads(json_text)

            # Validate structure
            if "pages" not in panel_data:
                raise ValueError("Missing 'pages' in response")

            # Assign global panel numbers
            global_panel_num = 1
            for page in panel_data["pages"]:
                for panel in page.get("panels", []):
                    panel["global_panel_num"] = global_panel_num
                    global_panel_num += 1

            return panel_data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response text: {response_text}")
            raise
        except Exception as e:
            logger.error(f"Failed to parse response: {e}")
            raise

    def breakdown_all_chapters(
        self,
        project_spec: Dict,
        story_text: str
    ) -> List[Dict]:
        """
        Break down all chapters in the project.

        Args:
            project_spec: Project specification
            story_text: Full story text

        Returns:
            List of panel breakdowns for each chapter
        """
        chapters = project_spec.get("chapters", [])
        logger.info(f"Breaking down {len(chapters)} chapters...")

        all_breakdowns = []

        for chapter in chapters:
            try:
                breakdown = self.breakdown_chapter(chapter, story_text, project_spec)
                all_breakdowns.append(breakdown)

            except Exception as e:
                logger.error(f"Failed to break down chapter {chapter.get('number', '?')}: {e}")
                continue

        logger.info(f"Completed breakdown for {len(all_breakdowns)}/{len(chapters)} chapters")

        return all_breakdowns

    def save_breakdown(self, breakdown: Dict, output_path: str):
        """Save panel breakdown to JSON file."""
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(breakdown, f, indent=2, ensure_ascii=False)

            logger.info(f"Panel breakdown saved to: {output_path}")

        except Exception as e:
            logger.error(f"Failed to save breakdown: {e}")
            raise

    def load_breakdown(self, input_path: str) -> Dict:
        """Load panel breakdown from JSON file."""
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                breakdown = json.load(f)

            logger.info(f"Panel breakdown loaded from: {input_path}")
            return breakdown

        except Exception as e:
            logger.error(f"Failed to load breakdown: {e}")
            raise
