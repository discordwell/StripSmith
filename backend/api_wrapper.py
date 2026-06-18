"""Wrapper for comic generation pipeline with user-provided API keys."""

import sys
import asyncio
from pathlib import Path
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.analysis.normalizer import StoryNormalizer
from src.analysis.analyzer import NarrativeAnalyzer
from src.assets.templates import CharacterTemplateManager
from src.assets.generator import ImageGenerator
from src.panels.breakdown import PanelBreakdown
from src.compositor.layout import PageCompositor
from src.compositor.export import ComicExporter
from src.utils.logger import get_logger
from src.utils.pipeline import select_chapters, panel_image_name

from backend.jobs import JobManager, JobStatus

logger = get_logger("stripsmith.api_wrapper")


class ComicGenerator:
    """Wrapper for the comic generation pipeline that accepts user API keys."""

    def __init__(
        self,
        openai_api_key: str,
        anthropic_api_key: str,
        job_manager: JobManager,
        job_id: str
    ):
        """
        Initialize comic generator with user-provided API keys.

        Args:
            openai_api_key: User's OpenAI API key
            anthropic_api_key: User's Anthropic API key
            job_manager: Job manager instance
            job_id: Current job ID
        """
        self.openai_key = openai_api_key
        self.anthropic_key = anthropic_api_key
        self.job_manager = job_manager
        self.job_id = job_id

        self.temp_dir = Path("data/temp") / job_id
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Comic generator initialized for job {job_id}")

    async def generate_comic(
        self,
        story_text: str,
        style: Optional[str] = None,
        chapters: str = "all",
        output_format: str = "pdf"
    ) -> Path:
        """
        Run the complete comic generation pipeline.

        Args:
            story_text: Story content
            style: Art style (optional)
            chapters: Chapters to process (e.g., "1-3" or "all")
            output_format: Output format (pdf, png, cbz)

        Returns:
            Path to generated comic file
        """
        try:
            # Stage 0: Normalize story
            self._update_progress(5, "Normalizing story text...")
            normalizer = StoryNormalizer()
            normalized = normalizer.normalize(story_text)
            logger.info(f"Story normalized: {normalized['metadata']['word_count']} words")

            # Stage 1: Analyze story
            self._update_progress(10, "Analyzing story structure with Claude...")
            analyzer = NarrativeAnalyzer(api_key=self.anthropic_key)
            project_spec = analyzer.analyze(
                normalized['text'],
                user_style=style
            )

            # Save project spec
            spec_path = self.temp_dir / "project_spec.json"
            analyzer.save_project_spec(project_spec, str(spec_path))
            logger.info(f"Found {len(project_spec['chapters'])} chapters, {len(project_spec['characters'])} characters")

            # Stage 2: Generate character sheets
            self._update_progress(20, f"Generating character reference sheets ({len(project_spec['characters'])} characters)...")
            template_manager = CharacterTemplateManager()
            template_manager.create_all_templates(project_spec)

            generator = ImageGenerator(api_key=self.openai_key)
            char_output_dir = self.temp_dir / "character_sheets"

            for i, character in enumerate(project_spec['characters']):
                char_name = character['name']
                progress = 20 + int((i / len(project_spec['characters'])) * 10)
                self._update_progress(progress, f"Generating character sheet: {char_name}...")

                # Create prompts
                prompts = template_manager.create_character_sheet_prompts(char_name)

                # Generate images
                await asyncio.to_thread(
                    generator.generate_character_sheet,
                    character_name=char_name,
                    prompts=prompts,
                    output_dir=str(char_output_dir)
                )

            logger.info(f"Character sheets complete. Cost: ${generator.get_total_cost():.2f}")

            # Stage 3: Break down chapters into panels
            self._update_progress(35, "Breaking chapters into panels...")
            # Pass the user's key explicitly — the hosted backend has no
            # ANTHROPIC_API_KEY in its environment, so PanelBreakdown() with no
            # argument would raise "ANTHROPIC_API_KEY not found".
            panel_breakdown = PanelBreakdown(api_key=self.anthropic_key)

            # Process specified chapters (raises a friendly ValueError on a
            # malformed selector, which fails the job cleanly).
            chapters_to_process = select_chapters(chapters, project_spec['chapters'])

            all_breakdowns = []
            for i, chapter in enumerate(chapters_to_process):
                progress = 35 + int((i / len(chapters_to_process)) * 10)
                self._update_progress(progress, f"Processing chapter {chapter['number']}...")

                # Break down the *normalized* text — the analyzer indexed its
                # paragraphs (start_paragraph/end_paragraph), so the breakdown
                # must slice the same text or chapters extract the wrong spans.
                breakdown = panel_breakdown.breakdown_chapter(
                    chapter,
                    normalized['text'],
                    project_spec
                )
                all_breakdowns.append(breakdown)

                # Save breakdown
                breakdown_path = self.temp_dir / f"chapter_{chapter['number']}_panels.json"
                panel_breakdown.save_breakdown(breakdown, str(breakdown_path))

            total_panels = sum(
                sum(len(page['panels']) for page in bd['pages'])
                for bd in all_breakdowns
            )
            logger.info(f"Created {total_panels} panels across {len(all_breakdowns)} chapters")

            # Stage 4: Generate panel images
            self._update_progress(50, f"Generating panel images ({total_panels} panels)...")

            panels_dir = self.temp_dir / "panels"
            panels_dir.mkdir(exist_ok=True)

            # Build character prompt map
            character_prompts = template_manager.templates
            character_prompts = {name: t['base_prompt'] for name, t in character_prompts.items()}

            # Project art style is applied to every panel for a consistent look.
            art_style = project_spec.get('style', {}).get('art_style')

            panel_count = 0
            for breakdown in all_breakdowns:
                chapter_num = breakdown['chapter_number']

                for page in breakdown['pages']:
                    for panel in page['panels']:
                        panel_num = panel['global_panel_num']
                        panel_count += 1

                        progress = 50 + int((panel_count / total_panels) * 40)
                        self._update_progress(progress, f"Generating panel {panel_count}/{total_panels}...")

                        # Scope the filename by chapter: global_panel_num restarts
                        # at 1 each chapter, so an unscoped name would overwrite
                        # earlier chapters' panels in a multi-chapter comic.
                        output_path = panels_dir / panel_image_name(chapter_num, panel_num)

                        await asyncio.to_thread(
                            generator.generate_panel,
                            panel_data=panel,
                            character_prompts=character_prompts,
                            output_path=str(output_path),
                            style=art_style
                        )

            logger.info(f"All panels generated! Total cost: ${generator.get_total_cost():.2f}")

            # Stage 5: Compose pages
            self._update_progress(92, "Composing comic pages...")
            compositor = PageCompositor()
            exporter = ComicExporter()

            pages_dir = self.temp_dir / "pages"
            pages_dir.mkdir(exist_ok=True)

            composed_pages = []

            for breakdown in all_breakdowns:
                chapter_num = breakdown['chapter_number']

                for page in breakdown['pages']:
                    page_num = page['page_number']

                    # Get panel images for this page (same chapter-scoped names
                    # used when the panels were generated above).
                    panel_images = [
                        str(panels_dir / panel_image_name(chapter_num, p['global_panel_num']))
                        for p in page['panels']
                    ]

                    # Compose page
                    output_path = pages_dir / f"chapter_{chapter_num}_page_{page_num}.png"

                    await asyncio.to_thread(
                        compositor.compose_page,
                        page_data=page,
                        panel_images=panel_images,
                        output_path=str(output_path)
                    )

                    composed_pages.append(str(output_path))

            logger.info(f"Composed {len(composed_pages)} pages")

            # Export final comic
            self._update_progress(97, f"Exporting to {output_format.upper()}...")
            output_dir = Path("data/output") / self.job_id
            output_dir.mkdir(parents=True, exist_ok=True)

            if output_format == 'pdf':
                output_file = output_dir / "comic.pdf"
                await asyncio.to_thread(
                    exporter.export_to_pdf,
                    page_images=composed_pages,
                    output_path=str(output_file),
                    title="Generated Comic"
                )

            elif output_format == 'png':
                output_subdir = output_dir / "pages"
                await asyncio.to_thread(
                    exporter.export_to_images,
                    page_images=composed_pages,
                    output_dir=str(output_subdir),
                    prefix="page"
                )
                output_file = output_subdir

            elif output_format == 'cbz':
                output_file = output_dir / "comic.cbz"
                await asyncio.to_thread(
                    exporter.export_to_cbz,
                    page_images=composed_pages,
                    output_path=str(output_file)
                )

            self._update_progress(100, "Complete!")
            logger.info(f"Comic generation complete: {output_file}")
            logger.info(f"Total cost: ${generator.get_total_cost():.2f}")

            return output_file

        except Exception as e:
            logger.error(f"Comic generation failed: {e}", exc_info=True)
            raise

    def _update_progress(self, progress: int, stage: str):
        """Update job progress."""
        self.job_manager.update_job_status(
            self.job_id,
            JobStatus.PROCESSING,
            progress=progress,
            stage=stage
        )
        logger.info(f"[{progress}%] {stage}")
