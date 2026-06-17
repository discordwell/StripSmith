# Stripsmith

**Automated AI Comic Generation from Stories**

Transform your written stories into beautiful AI-generated comics with consistent characters, professional layouts, and speech bubbles.

---

## Features

- **Stage 0: Story Ingestion** - Clean and normalize your story text
- **Stage 1: Narrative Analysis** - AI extracts chapters, characters, scenes, and art style
- **Stage 2: Character Sheets** - Generate consistent reference art for all characters
- **Stage 3: Panel Breakdown** - AI converts chapters into comic panels with dialogue
- **Stage 4: Image Generation** - DALL-E 3 generates each panel with consistent characters
- **Stage 5: Composition** - Automatic page layout with speech bubbles and text

---

## Quick Start

### 1. Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

```bash
# Copy environment template
cp .env.example .env

# Add your API keys
# OPENAI_API_KEY=your-openai-api-key
# ANTHROPIC_API_KEY=your-anthropic-api-key
```

### 3. Generate Your First Comic

```bash
# Put your story in data/stories/my_story.txt

# Generate comic
python scripts/generate_comic.py data/stories/my_story.txt \
  --style "noir comic" \
  --output data/output/my_comic
```

---

## Architecture

### Pipeline Stages

```
Story Text
    ↓
[Stage 0] Normalize & Clean
    ↓
[Stage 1] Extract Structure (Claude API)
    ├── Chapters
    ├── Characters (visual descriptions)
    ├── Environments
    └── Art style
    ↓
[Stage 2] Generate Character Sheets (DALL-E 3)
    └── Reference images for consistency
    ↓
[User Review & Approval]
    ↓
[Stage 3] Chapter → Panels (Claude API)
    ├── Panel descriptions
    ├── Dialogue
    ├── Camera angles
    └── Page layouts
    ↓
[Stage 4] Generate Panel Images (DALL-E 3)
    └── Using character templates
    ↓
[Stage 5] Compose Pages
    ├── Place panels in layout
    ├── Add speech bubbles
    ├── Render text
    └── Export to PDF/PNG
```

---

## Project Structure

```
stripsmith/
├── src/
│   ├── analysis/          # Stage 0 & 1: Story analysis
│   │   ├── normalizer.py  # Clean story text
│   │   └── analyzer.py    # Extract structure (Claude)
│   ├── assets/            # Stage 2: Character sheet generation
│   │   ├── generator.py   # DALL-E 3 image generation
│   │   └── templates.py   # Character prompt templates
│   ├── panels/            # Stage 3: Panel breakdown
│   │   └── breakdown.py   # Chapter → panels (Claude)
│   ├── compositor/        # Stage 5: Page composition
│   │   ├── layout.py      # Panel placement
│   │   ├── bubbles.py     # Speech bubble generation
│   │   └── export.py      # PDF/PNG export
│   └── utils/
│       ├── config.py      # Configuration loader
│       └── logger.py      # Logging utilities
├── scripts/
│   └── generate_comic.py  # Main CLI tool
├── data/
│   ├── stories/           # Input stories
│   ├── output/            # Generated comics
│   └── temp/              # Intermediate files
├── config/
│   └── config.yaml        # Default configuration
└── tests/                 # Unit tests
```

---

## Configuration

Edit `config/config.yaml` to customize:

```yaml
# Image generation
image:
  provider: "dalle3"       # or "stable-diffusion"
  size: "1024x1024"
  quality: "standard"      # or "hd"

# Panel layout
layout:
  default: "3-panel-grid"
  gutter: 10               # pixels between panels
  margin: 20               # page margin

# Speech bubbles
bubbles:
  font: "ComicSans"
  size: 14
  padding: 10

# Character consistency
characters:
  max_per_panel: 3         # Limit for better quality
  prompt_template: "{style}, {name}, {age}, {appearance}, {clothing}"
```

---

## Usage Examples

### Basic Usage

```bash
python scripts/generate_comic.py my_story.txt
```

### With Options

```bash
python scripts/generate_comic.py my_story.txt \
  --style "manga, black and white" \
  --chapters 1-3 \
  --review \
  --output-format pdf
```

### Step-by-Step Workflow

```bash
# Step 1: Analyze story
python scripts/generate_comic.py my_story.txt --analyze-only

# Review data/temp/project_spec.json

# Step 2: Generate character sheets
python scripts/generate_comic.py my_story.txt --characters-only

# Review data/temp/character_sheets/

# Step 3: Generate full comic
python scripts/generate_comic.py my_story.txt --from-analysis
```

---

## Cost Estimates

**DALL-E 3 Pricing:**
- Standard (1024×1024): $0.040 per image
- HD (1024×1024): $0.080 per image

**Typical 30-panel chapter:**
- Character sheets: 9 images × $0.04 = $0.36
- Panels: 30 images × $0.04 = $1.20
- **Total: ~$1.56 per chapter**

**Claude API:**
- Analysis: ~$0.05 per story
- Panel breakdown: ~$0.02 per chapter

**Grand total: ~$1.60-2.00 per chapter**

---

## Tips for Best Results

### Character Consistency

1. **Provide detailed character descriptions** in your story
2. **Use consistent names** (not "Sarah" then "the detective")
3. **Keep ≤3 characters per panel** for better quality
4. **Review character sheets** before generating panels

### Panel Quality

1. **Clear action descriptions** help the AI
2. **Separate dialogue from narration**
3. **Indicate camera angles** ("close-up on Sarah's face")
4. **Use consistent art style keywords**

### Story Structure

```
Good:
Sarah burst through the door. "We need to talk," she said, breathless.

Better:
[Close-up] Sarah burst through the door, her blonde hair wild, green eyes fierce.
[Mid-shot] "We need to talk," she said, catching her breath.
```

---

## Troubleshooting

### Character Inconsistency

- Make sure character descriptions are detailed
- Check character sheet images before generating panels
- Use the same exact character template in every prompt

### Poor Image Quality

- Try `--quality hd` (costs 2x)
- Add more style keywords: "professional comic art, detailed linework"
- Regenerate specific panels with `--regenerate 1,5,10`

### Layout Issues

- Adjust panel layouts in `config/config.yaml`
- Use `--layout splash` for important scenes
- Check `data/temp/panel_layouts.json` for generated layouts

---

## Testing

Unit tests live in `tests/` and run with [pytest](https://pytest.org):

```bash
pip install -r requirements.txt   # includes pytest
pytest                            # run the full suite
pytest tests/test_normalizer.py   # run a single module
```

The suite covers story normalization (including smart-quote handling),
configuration loading, character templating, page-layout geometry, the in-memory
job/session manager, and the web pipeline's API-key wiring. It runs fully offline
— no API keys or network access required.

---

## Development Roadmap

### MVP (Current)
- [x] Project structure
- [ ] Story normalization
- [ ] Claude-based analysis
- [ ] DALL-E 3 integration
- [ ] Basic grid layout
- [ ] Manual speech bubbles

### Phase 2
- [ ] Automatic speech bubble placement
- [ ] Multiple layout templates
- [ ] Style library (noir, manga, superhero, etc.)
- [ ] Batch processing
- [ ] Web UI

### Phase 3
- [ ] Stable Diffusion + LoRA option
- [ ] Character consistency fine-tuning
- [ ] Advanced layouts (splash pages, webtoon)
- [ ] Multi-language support
- [ ] Comic book export (.cbz)

---

## Contributing

This is a personal project, but suggestions are welcome! Open an issue to discuss major changes.

---

## License

MIT License - See LICENSE file for details

---

## Credits

- **DALL-E 3** by OpenAI - Image generation
- **Claude (Opus 4.8)** by Anthropic - Story analysis (configurable in `config/config.yaml`)
- **Pillow** - Image processing
- **ReportLab** - PDF generation

---

**Ready to turn your stories into comics!** 📖 → 📚
