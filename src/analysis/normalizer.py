"""Story text normalization and cleaning (Stage 0)."""

import re
from typing import Any, Dict, List, Optional
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger("stripsmith.normalizer")


class StoryNormalizer:
    """Normalize and clean story text for processing."""

    def __init__(self):
        """Initialize story normalizer.

        The curly/angle dialogue patterns use *named* Unicode escapes for the
        same reason ``_normalize_quotes`` does: written as literal curly
        characters they can be silently flattened to ASCII on save (the "Smart
        quotes" pattern here had in fact degenerated into a duplicate of the
        ASCII double-quote one), making them dead. In normal use these run after
        ``_normalize_quotes`` has already converted curly/angle quotes to ASCII,
        but keeping them correct means ``_annotate_dialogue`` still detects
        quoted speech if it is ever handed un-normalized text.
        """
        self.dialogue_patterns = [
            r'"([^"]+)"',           # Double quotes (ASCII)
            r"'([^']+)'",           # Single quotes (ASCII)
            # Smart double quotes “...”
            "\N{LEFT DOUBLE QUOTATION MARK}([^\N{RIGHT DOUBLE QUOTATION MARK}]+)"
            "\N{RIGHT DOUBLE QUOTATION MARK}",
            # French angle quotes «...»
            "\N{LEFT-POINTING DOUBLE ANGLE QUOTATION MARK}"
            "([^\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}]+)"
            "\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}",
        ]

    def normalize_file(self, file_path: str) -> Dict[str, Any]:
        """
        Load and normalize a story file.

        Args:
            file_path: Path to story text file

        Returns:
            Dict with normalized text and metadata
        """
        logger.info(f"Loading story from: {file_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_text = f.read()

            normalized = self.normalize(raw_text)

            return {
                "raw_text": raw_text,
                "normalized_text": normalized["text"],
                "metadata": normalized["metadata"],
                "source_file": str(Path(file_path).name)
            }

        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            raise
        except Exception as e:
            logger.error(f"Error loading file: {e}")
            raise

    def normalize(self, text: str) -> Dict[str, Any]:
        """
        Normalize story text.

        Args:
            text: Raw story text

        Returns:
            Dict with normalized text and metadata

        Normalization steps:
        1. Clean whitespace
        2. Normalize quotes
        3. Identify dialogue vs narration
        4. Split into paragraphs
        5. Detect POV markers
        6. Extract structure hints
        """
        logger.info("Normalizing story text...")

        # Step 1: Clean whitespace
        text = self._clean_whitespace(text)

        # Step 2: Normalize quotes
        text = self._normalize_quotes(text)

        # Step 3: Split into paragraphs
        paragraphs = self._split_paragraphs(text)

        # Step 4: Detect structure
        structure = self._detect_structure(paragraphs)

        # Step 5: Identify dialogue
        annotated = self._annotate_dialogue(paragraphs)

        # Step 6: Extract metadata
        metadata = self._extract_metadata(text, structure)

        normalized_text = "\n\n".join(annotated)

        logger.info(f"Normalization complete: {len(paragraphs)} paragraphs")

        return {
            "text": normalized_text,
            "paragraphs": annotated,
            "structure": structure,
            "metadata": metadata
        }

    def _clean_whitespace(self, text: str) -> str:
        """Clean excessive whitespace."""
        # Remove multiple spaces
        text = re.sub(r' +', ' ', text)

        # Remove trailing whitespace
        text = re.sub(r' +\n', '\n', text)

        # Normalize line breaks (max 2 consecutive)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Remove leading/trailing whitespace
        text = text.strip()

        return text

    def _normalize_quotes(self, text: str) -> str:
        """Normalize various quote styles to standard ASCII quotes.

        The keys use *named* Unicode escapes (the backslash-N form) rather than
        literal curly characters on purpose. An editor -- or a previous save of
        this file -- can silently flatten literal curly quotes to ASCII, turning
        every replacement into a no-op so real curly quotes from word processors
        are never normalized, which in turn makes dialogue detection miss quoted
        speech. Named escapes keep the source pure ASCII and immune to that.
        """
        replacements = {
            "\N{LEFT DOUBLE QUOTATION MARK}": '"',
            "\N{RIGHT DOUBLE QUOTATION MARK}": '"',
            "\N{LEFT SINGLE QUOTATION MARK}": "'",
            "\N{RIGHT SINGLE QUOTATION MARK}": "'",
            "\N{LEFT-POINTING DOUBLE ANGLE QUOTATION MARK}": '"',
            "\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}": '"',
        }

        for old, new in replacements.items():
            text = text.replace(old, new)

        return text

    def _split_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs."""
        # Split on double newlines
        paragraphs = text.split('\n\n')

        # Clean and filter empty paragraphs
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        return paragraphs

    def _detect_structure(self, paragraphs: List[str]) -> Dict[str, Any]:
        """
        Detect chapter breaks, scene breaks, etc.

        Looks for patterns like:
        - "Chapter 1"
        - "Chapter One:"
        - "---" (scene break)
        - "***" (scene break)
        """
        structure = {
            "chapter_markers": [],
            "scene_breaks": [],
            "has_chapters": False
        }

        chapter_pattern = re.compile(
            r'^(chapter|ch\.?)\s*(\d+|one|two|three|four|five|six|seven|eight|nine|ten)',
            re.IGNORECASE
        )

        scene_break_pattern = re.compile(r'^[-*#]{3,}$')

        for i, para in enumerate(paragraphs):
            # Check for chapter markers
            if chapter_pattern.match(para):
                structure["chapter_markers"].append(i)
                structure["has_chapters"] = True

            # Check for scene breaks
            if scene_break_pattern.match(para):
                structure["scene_breaks"].append(i)

        return structure

    def _annotate_dialogue(self, paragraphs: List[str]) -> List[str]:
        """
        Annotate paragraphs with dialogue markers.

        Returns paragraphs with [DIALOGUE] or [NARRATION] prefix.
        """
        annotated = []

        for para in paragraphs:
            # Check if paragraph contains dialogue
            has_dialogue = False
            for pattern in self.dialogue_patterns:
                if re.search(pattern, para):
                    has_dialogue = True
                    break

            if has_dialogue:
                # Mixed or pure dialogue
                if len(para.strip('"\'')) < len(para) * 0.8:
                    annotated.append(f"[DIALOGUE] {para}")
                else:
                    annotated.append(f"[MIXED] {para}")
            else:
                annotated.append(f"[NARRATION] {para}")

        return annotated

    def _extract_metadata(self, text: str, structure: Dict) -> Dict[str, Any]:
        """Extract metadata from the story."""
        return {
            "word_count": len(text.split()),
            "paragraph_count": len(text.split('\n\n')),
            "character_count": len(text),
            "has_chapters": structure["has_chapters"],
            "chapter_count": len(structure["chapter_markers"]),
            "scene_count": len(structure["scene_breaks"]) + 1
        }

    def extract_pov(self, text: str) -> str:
        """
        Detect point of view (first person, third person, etc.).

        Returns: "first", "second", or "third"
        """
        # Count POV indicators
        first_person = len(re.findall(r'\b(I|me|my|mine|we|us|our)\b', text, re.IGNORECASE))
        second_person = len(re.findall(r'\b(you|your|yours)\b', text, re.IGNORECASE))
        third_person = len(re.findall(r'\b(he|she|they|him|her|them|his|hers|their)\b', text, re.IGNORECASE))

        total = first_person + second_person + third_person
        if total == 0:
            return "unknown"

        # Return dominant POV
        if first_person / total > 0.4:
            return "first"
        elif second_person / total > 0.3:
            return "second"
        else:
            return "third"
