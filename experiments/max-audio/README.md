# Experimental Android AudioTrack probe

`MaxTone.java` generates a half-second 660 Hz mono tone at amplitude 500/32767
and applies per-track gain 0.25. It uses Android's music stream without changing
the system volume and releases the track after measuring playback head progress.
Successful progress is not evidence of audible output or a compatible bot backend.
The Max-specific Python wrapper verifies the SSH target, stages the dex archive in
a private temporary directory, and removes it on normal exit. The machine may
retain that directory after an abrupt disconnect, power failure, or termination.

The accompanying `max-tone.jar` is a ZIP containing `classes.dex`, built from
`MaxTone.java` using JDK 22 `javac --release 8` and Android R8/D8 8.3.37:

```
javac --release 8 -d build MaxTone.java
java -cp r8.jar com.android.tools.r8.D8 --min-api 28 --output max-tone.jar build/MaxTone.class
```

Build the standalone wrapper from the repository root with
`python scripts/build_max_probe.py tone --output max-tone-probe.pyz`.
It needs Python 3.10+ and an already working root SSH connection on the host;
it does not install the bot or LUNA. Android root access, AudioTrack permissions,
routing, sound level and cleanup on the real Max remain to be tested.
