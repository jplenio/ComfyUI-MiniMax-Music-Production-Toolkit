// Music Production Toolkit — cover song demos
//
// Each entry is one ORIGINAL track plus the covers made from it.
//
// HOW TO FILL THIS IN:
// 1. Upload the original and its covers to SoundCloud, make them publicly playable.
// 2. Paste the NORMAL SoundCloud track URL into "soundcloudUrl" (original and cover).
// 3. Optional: write something about the original into "comment".
// 4. Optional: the interpretation freedom you used into "freedom" (0-100) — the
//    production JSON does not record it, so it is empty until you type it in.
// 5. Put the cover images into docs/assets/demo-covers/ (see
//    scripts/prepare_demo_covers.py) and commit.
//
// "variant" is the toolkit's own export numbering: when the target file name already
// exists the saver appends _001, _002 … Those are separate runs of the same song, and
// the export title is identical for all of them - use "freedom" and the file name to
// tell them apart.
//
// Re-running scripts/update_cover_demo_catalog.py refreshes the facts from the
// production JSON and KEEPS everything you filled in by hand here.
//
window.DEMO_COVER_GROUPS = [
  {
    "id": "07-held-in-memory",
    "title": "07 Held in Memory",
    "sourceFile": "07 Held in Memory.flac",
    "sourceBpm": 65.0,
    "sourceDurationSeconds": 176.3,
    "soundcloudUrl": "https://soundcloud.com/pelenio/01-held-in-memory-original?in=pelenio/sets/music-production-toolkit-for",
    "comment": "",
    "covers": [
      {
        "id": "cover-demos-07-held-in-memory-cover",
        "title": "07 Held in Memory-cover",
        "variant": "Take 1",
        "file": "Cover Demos - 07 Held in Memory-cover.mp3",
        "soundcloudUrl": "https://soundcloud.com/pelenio/02-cover-demos-07-held-in?in=pelenio/sets/music-production-toolkit-for",
        "coverArt": "assets/demo-covers/Cover Demos - 07 Held in Memory-cover.jpg",
        "model": "YuE2 Cover",
        "genre": "Neoclassical",
        "tempoLabel": "Slow (40-70 BPM)",
        "styleTemplate": "classical/cinematic-romance.txt",
        "lyricsMode": "instrumental",
        "coverMode": "full",
        "leadInstrument": "Lead synth",
        "freedom": "",
        "targetDurationSeconds": 360.0,
        "seed": 4472451455570227022,
        "steps": 40,
        "cfg": 1.0,
        "sampler": "dpm_2",
        "scheduler": "sgm_uniform",
        "outputSampleRate": 44100,
        "scoreChanges": [
          "vocal_notes_replaced_with_rests; lead_blocks_moved_to_Ins:0",
          "original_Ins_notes_replaced_in_lead_blocks:0"
        ]
      },
      {
        "id": "cover-demos-07-held-in-memory-cover-001",
        "title": "07 Held in Memory-cover",
        "variant": "Take 2",
        "file": "Cover Demos - 07 Held in Memory-cover_001.mp3",
        "soundcloudUrl": "https://soundcloud.com/pelenio/03-cover-demos-07-held-in?in=pelenio/sets/music-production-toolkit-for",
        "coverArt": "assets/demo-covers/Cover Demos - 07 Held in Memory-cover_001.jpg",
        "model": "YuE2 Cover",
        "genre": "Electronic",
        "tempoLabel": "Midtempo (100-120 BPM)",
        "styleTemplate": "electronic/cinematic-electronica.txt",
        "lyricsMode": "instrumental",
        "coverMode": "full",
        "leadInstrument": "Lead synth",
        "freedom": "",
        "targetDurationSeconds": 360.0,
        "seed": 6477359647997814294,
        "steps": 40,
        "cfg": 1.0,
        "sampler": "dpm_2",
        "scheduler": "sgm_uniform",
        "outputSampleRate": 44100,
        "scoreChanges": [
          "vocal_notes_replaced_with_rests; lead_blocks_moved_to_Ins:0",
          "original_Ins_notes_replaced_in_lead_blocks:0"
        ]
      }
    ],
    "coverCount": 2
  },
  {
    "id": "16-mgb-bit-16",
    "title": "16 MGB Bit 16",
    "sourceFile": "16 MGB Bit 16.flac",
    "sourceBpm": 99.0,
    "sourceDurationSeconds": 221.2,
    "soundcloudUrl": "https://soundcloud.com/pelenio/04-16-mgb-bit-16-original?in=pelenio/sets/music-production-toolkit-for",
    "comment": "",
    "covers": [
      {
        "id": "cover-demos-16-mgb-bit-16-cover",
        "title": "16 MGB Bit 16-cover",
        "variant": "Take 1",
        "file": "Cover Demos - 16 MGB Bit 16-cover.mp3",
        "soundcloudUrl": "https://soundcloud.com/pelenio/05-cover-demos-16-mgb-bit-16?in=pelenio/sets/music-production-toolkit-for",
        "coverArt": "assets/demo-covers/Cover Demos - 16 MGB Bit 16-cover.jpg",
        "model": "YuE2 Cover",
        "genre": "Progressive Trance",
        "tempoLabel": "Dancefloor (120-130 BPM)",
        "styleTemplate": "edm/progressive-trance-instrumental.txt",
        "lyricsMode": "instrumental",
        "coverMode": "full",
        "leadInstrument": "Lead synth",
        "freedom": "",
        "targetDurationSeconds": 360.0,
        "seed": 3298344741090151905,
        "steps": 40,
        "cfg": 1.0,
        "sampler": "dpm_2",
        "scheduler": "sgm_uniform",
        "outputSampleRate": 44100,
        "scoreChanges": [
          "vocal_notes_replaced_with_rests; lead_blocks_moved_to_Ins:0",
          "original_Ins_notes_replaced_in_lead_blocks:0"
        ]
      },
      {
        "id": "cover-demos-16-mgb-bit-16-cover-001",
        "title": "16 MGB Bit 16-cover",
        "variant": "Take 2",
        "file": "Cover Demos - 16 MGB Bit 16-cover_001.mp3",
        "soundcloudUrl": "https://soundcloud.com/pelenio/06-cover-demos-16-mgb-bit-16?in=pelenio/sets/music-production-toolkit-for",
        "coverArt": "assets/demo-covers/Cover Demos - 16 MGB Bit 16-cover_001.jpg",
        "model": "YuE2 Cover",
        "genre": "Trip-Hop",
        "tempoLabel": "Laid-back (70-100 BPM)",
        "styleTemplate": "electronic/trip-hop.txt",
        "lyricsMode": "instrumental",
        "coverMode": "full",
        "leadInstrument": "Lead synth",
        "freedom": "",
        "targetDurationSeconds": 360.0,
        "seed": 1628516839357638628,
        "steps": 40,
        "cfg": 1.0,
        "sampler": "dpm_2",
        "scheduler": "sgm_uniform",
        "outputSampleRate": 44100,
        "scoreChanges": [
          "vocal_notes_replaced_with_rests; lead_blocks_moved_to_Ins:0",
          "original_Ins_notes_replaced_in_lead_blocks:0"
        ]
      }
    ],
    "coverCount": 2
  },
  {
    "id": "18-noname-iv",
    "title": "18 NoName IV",
    "sourceFile": "18 NoName IV.mp3",
    "sourceBpm": 166.0,
    "sourceDurationSeconds": 131.9,
    "soundcloudUrl": "https://soundcloud.com/pelenio/07-noname-iv-original?in=pelenio/sets/music-production-toolkit-for",
    "comment": "",
    "covers": [
      {
        "id": "cover-demos-18-noname-iv-cover",
        "title": "18 NoName IV-cover",
        "variant": "Take 1",
        "file": "Cover Demos - 18 NoName IV-cover.mp3",
        "soundcloudUrl": "https://soundcloud.com/pelenio/08-cover-demos-18-noname-iv?in=pelenio/sets/music-production-toolkit-for",
        "coverArt": "assets/demo-covers/Cover Demos - 18 NoName IV-cover.jpg",
        "model": "YuE2 Cover",
        "genre": "Progressive House",
        "tempoLabel": "Dancefloor (120-130 BPM)",
        "styleTemplate": "house/progressive-house-melodic-trance.txt",
        "lyricsMode": "instrumental",
        "coverMode": "full",
        "leadInstrument": "Trumpet",
        "freedom": "",
        "targetDurationSeconds": 360.0,
        "seed": 538948054291393876,
        "steps": 40,
        "cfg": 1.0,
        "sampler": "dpm_2",
        "scheduler": "sgm_uniform",
        "outputSampleRate": 44100,
        "scoreChanges": [
          "vocal_notes_replaced_with_rests; lead_blocks_moved_to_Ins:0",
          "original_Ins_notes_replaced_in_lead_blocks:0"
        ]
      },
      {
        "id": "cover-demos-18-noname-iv-cover-001",
        "title": "18 NoName IV-cover",
        "variant": "Take 2",
        "file": "Cover Demos - 18 NoName IV-cover_001.mp3",
        "soundcloudUrl": "https://soundcloud.com/pelenio/09-cover-demos-18-noname-iv?in=pelenio/sets/music-production-toolkit-for",
        "coverArt": "assets/demo-covers/Cover Demos - 18 NoName IV-cover_001.jpg",
        "model": "YuE2 Cover",
        "genre": "P-Funk / Classic Funk",
        "tempoLabel": "Midtempo (100-120 BPM)",
        "styleTemplate": "funk/classic-funk-instrumental.txt",
        "lyricsMode": "instrumental",
        "coverMode": "full",
        "leadInstrument": "Trumpet",
        "freedom": "",
        "targetDurationSeconds": 360.0,
        "seed": 8492767954634747245,
        "steps": 40,
        "cfg": 1.0,
        "sampler": "dpm_2",
        "scheduler": "sgm_uniform",
        "outputSampleRate": 44100,
        "scoreChanges": [
          "vocal_notes_replaced_with_rests; lead_blocks_moved_to_Ins:0",
          "original_Ins_notes_replaced_in_lead_blocks:0"
        ]
      },
      {
        "id": "cover-demos-18-noname-iv-cover-002",
        "title": "18 NoName IV-cover",
        "variant": "Take 3",
        "file": "Cover Demos - 18 NoName IV-cover_002.mp3",
        "soundcloudUrl": "https://soundcloud.com/pelenio/10-cover-demos-18-noname-iv?in=pelenio/sets/music-production-toolkit-for",
        "coverArt": "assets/demo-covers/Cover Demos - 18 NoName IV-cover_002.jpg",
        "model": "YuE2 Cover",
        "genre": "Ambient",
        "tempoLabel": "Slow (40-70 BPM)",
        "styleTemplate": "ambient/ambient-guitar.txt",
        "lyricsMode": "instrumental",
        "coverMode": "full",
        "leadInstrument": "Trumpet",
        "freedom": "",
        "targetDurationSeconds": 360.0,
        "seed": 393469552128309816,
        "steps": 40,
        "cfg": 1.0,
        "sampler": "dpm_2",
        "scheduler": "sgm_uniform",
        "outputSampleRate": 44100,
        "scoreChanges": [
          "vocal_notes_replaced_with_rests; lead_blocks_moved_to_Ins:0",
          "original_Ins_notes_replaced_in_lead_blocks:0"
        ]
      },
      {
        "id": "cover-demos-18-noname-iv-cover-003",
        "title": "18 NoName IV-cover",
        "variant": "Take 4",
        "file": "Cover Demos - 18 NoName IV-cover_003.mp3",
        "soundcloudUrl": "https://soundcloud.com/pelenio/11-cover-demos-18-noname-iv?in=pelenio/sets/music-production-toolkit-for",
        "coverArt": "assets/demo-covers/Cover Demos - 18 NoName IV-cover_003.jpg",
        "model": "YuE2 Cover",
        "genre": "Symphonic / Orchestral",
        "tempoLabel": "Midtempo (100-120 BPM)",
        "styleTemplate": "classical/symphonic-orchestral-instrumental.txt",
        "lyricsMode": "instrumental",
        "coverMode": "full",
        "leadInstrument": "Trumpet",
        "freedom": "",
        "targetDurationSeconds": 360.0,
        "seed": 1606534039465470346,
        "steps": 40,
        "cfg": 1.0,
        "sampler": "dpm_2",
        "scheduler": "sgm_uniform",
        "outputSampleRate": 44100,
        "scoreChanges": [
          "vocal_notes_replaced_with_rests; lead_blocks_moved_to_Ins:0",
          "original_Ins_notes_replaced_in_lead_blocks:0"
        ]
      }
    ],
    "coverCount": 4
  }
];
