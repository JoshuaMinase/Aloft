# ADR 0004: Use ElevenLabs for Text-to-Speech

## Status

Accepted

## Context

The Aloft application requires high-quality text-to-speech (TTS) for:

- POI narration audio generation
- Natural-sounding voice for tour guides
- Multiple voice options for different content types
- Fast synthesis for real-time content generation

Requirements:

- High audio quality
- Natural intonation and pronunciation
- Fast synthesis time
- Cost-effective for free tier
- Easy API integration

## Decision

We will use **ElevenLabs** for text-to-speech synthesis.

### Rationale

1. **Audio Quality**: Industry-leading natural-sounding voices
2. **Free Tier**: Generous free tier with no credit card required
3. **Voice Variety**: Multiple voices with different characteristics
4. **Fast Synthesis**: Quick API response times
5. **Easy Integration**: Simple REST API with good documentation
6. **Scalability**: Can handle increased load as needed

### Alternatives Considered

- **Google Cloud TTS**: Requires credit card, higher cost
- **Amazon Polly**: Requires AWS account, complex setup
- **Microsoft Azure TTS**: Requires Azure account, higher cost
- **OpenAI TTS**: Good quality but requires OpenAI account, limited free tier

## Consequences

### Positive

- Excellent audio quality for user experience
- Free tier suitable for development and initial production
- Easy to integrate with existing codebase
- Multiple voice options for content variety
- Good documentation and support

### Negative

- Vendor lock-in (ElevenLabs-specific voices)
- API limits on free tier
- Requires internet connection for synthesis
- Potential cost increase at scale

## Implementation

ElevenLabs is accessed via HTTP requests using the httpx library:
```
httpx==0.28.1
```

Audio synthesis is implemented in `app/services/audio_synthesis.py` with configuration in `app/core/config.py`.

## Voice Configuration

Default voice: "Bella" (free tier voice)

Additional voices can be configured via:
```
ELEVENLABS_VOICE_ID=your-voice-id
```

## References

- [ElevenLabs Documentation](https://elevenlabs.io/docs)
- [ElevenLabs API Reference](https://api.elevenlabs.io/)
- [ElevenLabs Voice Library](https://elevenlabs.io/voice-lab)
