<!-- Lazy-loaded: only read when handling image/video/audio tasks -->

## Image generation
- Describe scenes in natural language (subject, context, style, lighting, mood).
- Photorealistic: specify shot type, camera angle, lens, lighting.
- Stylized: be explicit (watercolor, vector, pixel art, etc.).
- Text in images: specify exact text, font style, placement.
- Resolutions: 512px, 1K, 2K, 4K. Aspects: 1:1, 16:9, 9:16, 3:2, 4:3.
- All images include SynthID watermarking.
- Deliver via message tool with `media/path/filePath` or `MEDIA:` directive.

## Video generation
- Include: subject, action, style, camera motion, composition, ambiance.
- Camera movements: dolly, aerial, tracking, static.
- Audio: quotation marks for dialogue, describe sound effects.
- Negative prompts as keywords (not instructions).
- Formats: 16:9 (landscape), 9:16 (portrait). Resolutions: 720p, 1080p, 4K.
- Duration: 4, 6, or 8 seconds. Extensions up to ~148s.
- Latency: 11s to 6 min. Retained 2 days — deliver promptly.

## Media understanding
- Image: analysis, OCR, description, comparison.
- Video: summarization, scene analysis.
- Audio: transcription, summary.
- For complex analysis: describe first, then analyze.
