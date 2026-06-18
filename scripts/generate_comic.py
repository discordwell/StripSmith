#!/usr/bin/env python3
"""Main CLI for Stripsmith comic generation."""

import sys
import os
import click
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv(project_root / ".env")

from src.analysis.normalizer import StoryNormalizer
from src.analysis.analyzer import NarrativeAnalyzer
from src.assets.templates import CharacterTemplateManager
from src.assets.generator import ImageGenerator
from src.panels.breakdown import PanelBreakdown
from src.compositor.layout import PageCompositor
from src.compositor.export import ComicExporter
from src.utils.logger import setup_logger, get_logger
from src.utils.config import get_config
from src.utils.pipeline import select_chapters, panel_image_name

# Setup logger
setup_logger(name="stripsmith", level="INFO", console=True)
logger = get_logger("stripsmith")


@click.group()
def cli():
    """Stripsmith: AI Comic Generation from Stories"""
    pass


@cli.command()
@click.argument('story_file', type=click.Path(exists=True))
@click.option('--style', default=None, help='Art style (e.g., "noir comic", "manga")')
@click.option('--output', '-o', default='data/output', help='Output directory')
@click.option('--format', type=click.Choice(['pdf', 'png', 'cbz']), default='pdf', help='Output format')
@click.option('--chapters', default=None, help='Chapters to process (e.g., "1-3" or "all")')
@click.option('--analyze-only', is_flag=True, help='Only analyze story, don\'t generate images')
@click.option('--characters-only', is_flag=True, help='Only generate character sheets')
def generate(story_file, style, output, format, chapters, analyze_only, characters_only):
    """
    Generate a comic from a story file.

    STORY_FILE: Path to your story text file
    """
    try:
        click.echo("=" * 60)
        click.echo("STRIPSMITH - AI Comic Generation")
        click.echo("=" * 60)
        click.echo()

        config = get_config()

        # Stage 0: Normalize story
        click.echo("📖 Stage 0: Loading and normalizing story...")
        normalizer = StoryNormalizer()
        normalized = normalizer.normalize_file(story_file)

        click.echo(f"  ✓ Loaded: {normalized['metadata']['word_count']} words, "
                  f"{normalized['metadata']['paragraph_count']} paragraphs")
        click.echo()

        # Stage 1: Analyze story
        click.echo("🔍 Stage 1: Analyzing story structure...")
        analyzer = NarrativeAnalyzer()
        project_spec = analyzer.analyze(
            normalized['normalized_text'],
            user_style=style
        )

        click.echo(f"  ✓ Found: {len(project_spec['chapters'])} chapters")
        click.echo(f"  ✓ Found: {len(project_spec['characters'])} characters")
        click.echo(f"  ✓ Art style: {project_spec['style']['art_style']}")
        click.echo()

        # Save project spec
        temp_dir = Path("data/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)
        spec_path = temp_dir / "project_spec.json"
        analyzer.save_project_spec(project_spec, str(spec_path))
        click.echo(f"  💾 Saved project spec: {spec_path}")
        click.echo()

        if analyze_only:
            click.echo("✓ Analysis complete! Review the project spec and run again without --analyze-only")
            return

        # Stage 2: Generate character sheets
        click.echo("👤 Stage 2: Generating character reference sheets...")
        template_manager = CharacterTemplateManager()
        template_manager.create_all_templates(project_spec)

        generator = ImageGenerator()

        char_output_dir = temp_dir / "character_sheets"

        for character in project_spec['characters']:
            char_name = character['name']
            click.echo(f"  Generating: {char_name}...")

            # Create prompts
            prompts = template_manager.create_character_sheet_prompts(char_name)

            # Generate images
            generator.generate_character_sheet(
                character_name=char_name,
                prompts=prompts,
                output_dir=str(char_output_dir)
            )

        click.echo(f"  ✓ Character sheets saved to: {char_output_dir}")
        click.echo(f"  💰 Cost so far: ${generator.get_total_cost():.2f}")
        click.echo()

        if characters_only:
            click.echo("✓ Character sheets complete! Review them and run again without --characters-only")
            return

        # Stage 3: Break down chapters into panels
        click.echo("📋 Stage 3: Breaking chapters into panels...")
        panel_breakdown = PanelBreakdown()

        # Process specified chapters (validates the --chapters selector)
        chapters_to_process = select_chapters(chapters, project_spec['chapters'])

        all_breakdowns = []
        for chapter in chapters_to_process:
            click.echo(f"  Processing chapter {chapter['number']}...")
            # Break down the *normalized* text the analyzer indexed, so chapter
            # start/end paragraph indices line up with the text being sliced.
            breakdown = panel_breakdown.breakdown_chapter(
                chapter,
                normalized['normalized_text'],
                project_spec
            )
            all_breakdowns.append(breakdown)

            # Save breakdown
            breakdown_path = temp_dir / f"chapter_{chapter['number']}_panels.json"
            panel_breakdown.save_breakdown(breakdown, str(breakdown_path))

        total_panels = sum(
            sum(len(page['panels']) for page in bd['pages'])
            for bd in all_breakdowns
        )

        click.echo(f"  ✓ Created {total_panels} panels across {len(all_breakdowns)} chapters")
        click.echo()

        # Stage 4: Generate panel images
        click.echo("🎨 Stage 4: Generating panel images...")
        click.echo(f"  (This will cost approximately ${total_panels * 0.04:.2f})")

        if not click.confirm("  Continue with image generation?"):
            click.echo("  Cancelled. Run again when ready.")
            return

        panels_dir = temp_dir / "panels"
        panels_dir.mkdir(exist_ok=True)

        # Build character prompt map
        character_prompts = template_manager.templates
        character_prompts = {name: t['base_prompt'] for name, t in character_prompts.items()}

        # Project art style applied to every panel for a consistent look.
        art_style = project_spec.get('style', {}).get('art_style')

        for breakdown in all_breakdowns:
            chapter_num = breakdown['chapter_number']

            for page in breakdown['pages']:
                for panel in page['panels']:
                    panel_num = panel['global_panel_num']
                    click.echo(f"  Generating chapter {chapter_num} panel {panel_num}...")

                    # Chapter-scoped name: panel numbering restarts per chapter.
                    output_path = panels_dir / panel_image_name(chapter_num, panel_num)

                    generator.generate_panel(
                        panel_data=panel,
                        character_prompts=character_prompts,
                        output_path=str(output_path),
                        style=art_style
                    )

        click.echo(f"  ✓ All panels generated!")
        click.echo(f"  💰 Total cost: ${generator.get_total_cost():.2f}")
        click.echo()

        # Stage 5: Compose pages
        click.echo("📄 Stage 5: Composing comic pages...")
        compositor = PageCompositor()
        exporter = ComicExporter()

        pages_dir = temp_dir / "pages"
        pages_dir.mkdir(exist_ok=True)

        composed_pages = []

        for breakdown in all_breakdowns:
            chapter_num = breakdown['chapter_number']

            for page in breakdown['pages']:
                page_num = page['page_number']
                layout = page['layout']

                # Get panel images for this page (chapter-scoped, matching how
                # they were written in Stage 4).
                panel_images = [
                    str(panels_dir / panel_image_name(chapter_num, p['global_panel_num']))
                    for p in page['panels']
                ]

                # Compose page
                output_path = pages_dir / f"chapter_{chapter_num}_page_{page_num}.png"

                compositor.compose_page(
                    page_data=page,
                    panel_images=panel_images,
                    output_path=str(output_path)
                )

                composed_pages.append(str(output_path))

        click.echo(f"  ✓ Composed {len(composed_pages)} pages")
        click.echo()

        # Export final comic
        click.echo(f"📦 Exporting to {format.upper()}...")
        output_dir = Path(output)
        output_dir.mkdir(parents=True, exist_ok=True)

        story_name = Path(story_file).stem

        if format == 'pdf':
            output_file = output_dir / f"{story_name}.pdf"
            exporter.export_to_pdf(
                page_images=composed_pages,
                output_path=str(output_file),
                title=story_name
            )
            click.echo(f"  ✓ PDF saved: {output_file}")

        elif format == 'png':
            output_subdir = output_dir / story_name
            exporter.export_to_images(
                page_images=composed_pages,
                output_dir=str(output_subdir),
                prefix="page"
            )
            click.echo(f"  ✓ Images saved: {output_subdir}")

        elif format == 'cbz':
            output_file = output_dir / f"{story_name}.cbz"
            exporter.export_to_cbz(
                page_images=composed_pages,
                output_path=str(output_file)
            )
            click.echo(f"  ✓ CBZ saved: {output_file}")

        click.echo()
        click.echo("=" * 60)
        click.echo("✨ COMIC GENERATION COMPLETE! ✨")
        click.echo("=" * 60)
        click.echo(f"Total cost: ${generator.get_total_cost():.2f}")
        click.echo()

    except Exception as e:
        logger.error(f"Comic generation failed: {e}")
        click.echo(f"\n❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
def test():
    """Test API connections."""
    click.echo("Testing API connections...")
    click.echo()

    # Test Anthropic API
    try:
        click.echo("Testing Claude API...")
        analyzer = NarrativeAnalyzer()
        click.echo("  ✓ Claude API connected")
    except Exception as e:
        click.echo(f"  ❌ Claude API failed: {e}")

    # Test OpenAI API
    try:
        click.echo("Testing OpenAI API...")
        generator = ImageGenerator()
        click.echo("  ✓ OpenAI API connected")
    except Exception as e:
        click.echo(f"  ❌ OpenAI API failed: {e}")

    click.echo()
    click.echo("✓ API test complete!")


if __name__ == "__main__":
    cli()
