"""Narrative analysis using Claude API (Stage 1)."""

import json
import os
from typing import Dict, List, Optional
from anthropic import Anthropic

from src.utils.logger import get_logger
from src.utils.config import get_config, DEFAULT_LLM_MODEL, DEFAULT_LLM_MAX_TOKENS

logger = get_logger("stripsmith.analyzer")


class NarrativeAnalyzer:
    """Analyze story structure and extract characters, scenes, and style using Claude."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize narrative analyzer.

        Args:
            api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if None)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment")

        self.client = Anthropic(api_key=self.api_key)
        self.config = get_config()

        logger.info("Narrative analyzer initialized")

    def analyze(self, story_text: str, user_style: Optional[str] = None) -> Dict:
        """
        Analyze story and extract structure.

        Args:
            story_text: Normalized story text
            user_style: Optional user-specified art style

        Returns:
            Project spec with chapters, characters, environments, style
        """
        logger.info("Analyzing story structure...")

        # Build analysis prompt
        prompt = self._build_analysis_prompt(story_text, user_style)

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
            project_spec = self._parse_response(result_text)

            logger.info(f"Analysis complete: {len(project_spec['chapters'])} chapters, "
                       f"{len(project_spec['characters'])} characters")

            return project_spec

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            raise

    def _build_analysis_prompt(self, story_text: str, user_style: Optional[str]) -> str:
        """Build the analysis prompt for Claude."""

        style_instruction = ""
        if user_style:
            style_instruction = f"\n- Use the following art style: {user_style}"
        else:
            style_instruction = "\n- Infer an appropriate art style from the story genre and tone"

        prompt = f"""Analyze this story and extract its structure for comic book generation.

Story:
{story_text}

Please provide a JSON response with the following structure:

{{
  "chapters": [
    {{
      "number": 1,
      "title": "Chapter title or description",
      "summary": "Brief summary of events",
      "start_paragraph": 0,
      "end_paragraph": 10
    }}
  ],
  "characters": [
    {{
      "name": "Character Name",
      "role": "protagonist/antagonist/supporting",
      "age": "age range (e.g., 'mid-30s', 'teenage', 'elderly')",
      "gender": "male/female/non-binary",
      "physical_features": "Detailed physical description (hair color, eye color, height, build, distinctive features)",
      "clothing": "Typical clothing style and items",
      "accessories": "Recurring props or accessories (glasses, weapon, jewelry, etc.)",
      "personality": "Brief personality description (optional, for context)"
    }}
  ],
  "environments": [
    {{
      "name": "Location name",
      "description": "Visual description of the environment",
      "recurring": true/false
    }}
  ],
  "style": {{
    "art_style": "Comic art style (e.g., 'noir comic', 'manga', 'superhero comic', 'European BD', 'webtoon')",
    "color_palette": "Color scheme (e.g., 'high contrast black and white', 'muted earth tones', 'vibrant colors')",
    "mood": "Overall mood/tone (e.g., 'dark and gritty', 'lighthearted', 'epic')",
    "era": "Time period if relevant (e.g., '1940s', 'futuristic', 'medieval')"
  }}
}}

Instructions:
- Break the story into logical chapters/scenes (aim for {self.config.get('analysis.max_chapters', 50)} max)
- Extract ALL named characters with detailed visual descriptions
- Include recurring locations and environments
{style_instruction}
- Focus on VISUAL details that can be drawn (not personality traits unless they affect appearance)
- For characters, be extremely specific about visual features (exact hair length, eye color, clothing items)
- Use paragraph indices from the story text for chapter boundaries

Return ONLY the JSON, no additional text."""

        return prompt

    def _parse_response(self, response_text: str) -> Dict:
        """Parse Claude's JSON response."""
        try:
            # Extract JSON from response (in case there's extra text)
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1

            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in response")

            json_text = response_text[json_start:json_end]
            project_spec = json.loads(json_text)

            # Validate structure
            required_keys = ["chapters", "characters", "environments", "style"]
            for key in required_keys:
                if key not in project_spec:
                    raise ValueError(f"Missing required key: {key}")

            return project_spec

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response text: {response_text}")
            raise
        except Exception as e:
            logger.error(f"Failed to parse response: {e}")
            raise

    def validate_project_spec(self, project_spec: Dict) -> bool:
        """
        Validate project specification.

        Args:
            project_spec: Project spec to validate

        Returns:
            True if valid
        """
        try:
            # Check chapters
            if not project_spec.get("chapters"):
                logger.error("No chapters found")
                return False

            # Check characters
            if not project_spec.get("characters"):
                logger.warning("No characters found")

            # Validate character structure
            for char in project_spec.get("characters", []):
                required = ["name", "physical_features", "clothing"]
                if not all(key in char for key in required):
                    logger.error(f"Character missing required fields: {char.get('name', 'unknown')}")
                    return False

            # Check style
            if not project_spec.get("style"):
                logger.error("No style information found")
                return False

            logger.info("Project spec validation passed")
            return True

        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False

    def save_project_spec(self, project_spec: Dict, output_path: str):
        """
        Save project specification to JSON file.

        Args:
            project_spec: Project spec to save
            output_path: Path to save JSON file
        """
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(project_spec, f, indent=2, ensure_ascii=False)

            logger.info(f"Project spec saved to: {output_path}")

        except Exception as e:
            logger.error(f"Failed to save project spec: {e}")
            raise

    def load_project_spec(self, input_path: str) -> Dict:
        """
        Load project specification from JSON file.

        Args:
            input_path: Path to JSON file

        Returns:
            Project spec dict
        """
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                project_spec = json.load(f)

            logger.info(f"Project spec loaded from: {input_path}")
            return project_spec

        except Exception as e:
            logger.error(f"Failed to load project spec: {e}")
            raise
