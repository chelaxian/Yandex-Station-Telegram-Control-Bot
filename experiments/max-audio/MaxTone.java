// Standalone Android 9 playback probe. Reflection avoids bundling Android classes.
public final class MaxTone {
    public static void main(String[] args) {
        Object track = null;
        boolean ok = false;
        try {
            Class<?> cls = Class.forName("android.media.AudioTrack");
            int rate = 48000, frames = 24000;
            short[] samples = new short[frames];
            for (int i = 0; i < frames; i++) {
                double fade = Math.min(1.0, Math.min(i / 1200.0, (frames - 1 - i) / 1200.0));
                samples[i] = (short)(500 * fade * Math.sin(2 * Math.PI * 660 * i / rate));
            }
            // STREAM_MUSIC, CHANNEL_OUT_MONO, ENCODING_PCM_16BIT, MODE_STATIC.
            track = cls.getConstructor(int.class, int.class, int.class, int.class, int.class, int.class)
                .newInstance(3, rate, 4, 2, frames * 2, 0);
            int state = (Integer) cls.getMethod("getState").invoke(track);
            if (state != 2 && state != 1) throw new IllegalStateException("track state=" + state);
            int wrote = (Integer) cls.getMethod("write", short[].class, int.class, int.class)
                .invoke(track, samples, 0, frames);
            if (wrote != frames) throw new IllegalStateException("short write=" + wrote);
            int gain = (Integer) cls.getMethod("setVolume", float.class).invoke(track, 0.25f);
            if (gain != 0) throw new IllegalStateException("gain=" + gain);
            cls.getMethod("play").invoke(track);
            Thread.sleep(1000);
            int played = (Integer) cls.getMethod("getPlaybackHeadPosition").invoke(track);
            System.out.println("MAX_TONE_RESULT written=" + wrote + " played=" + played);
            if (played <= 0) throw new IllegalStateException("no progress");
            ok = true;
        } catch (Throwable error) {
            if (error instanceof java.lang.reflect.InvocationTargetException && error.getCause() != null) {
                error = error.getCause();
            }
            System.err.println("MAX_TONE_ERROR " + error.getClass().getName() + ": " + error.getMessage());
        } finally {
            if (track != null) {
                try { track.getClass().getMethod("release").invoke(track); } catch (Throwable ignored) { }
            }
        }
        if (!ok) System.exit(1);
    }
}
