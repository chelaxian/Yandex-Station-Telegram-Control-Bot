// Standalone Android 9 WAV player for the experimental Station Max backend.
// Reflection avoids bundling Android classes. Cancellation: the caller creates the stop file.
import java.io.File;
import java.io.RandomAccessFile;

public final class MaxPlay {
    private static final int CHUNK = 8192;

    public static void main(String[] args) {
        Object track = null;
        int exit = 1;
        try {
            if (args.length != 2) throw new IllegalArgumentException("usage: MaxPlay <wav> <stopfile>");
            File stop = new File(args[1]);
            RandomAccessFile raf = new RandomAccessFile(args[0], "r");
            int rate = 0, channels = 0, bits = 0, format = 0;
            long dataStart = -1, dataLen = 0;
            try {
                byte[] head = new byte[12];
                raf.readFully(head);
                if (!new String(head, 0, 4, "US-ASCII").equals("RIFF") || !new String(head, 8, 4, "US-ASCII").equals("WAVE"))
                    throw new IllegalArgumentException("not a RIFF/WAVE file");
                while (raf.getFilePointer() + 8 <= raf.length()) {
                    byte[] ch = new byte[8];
                    raf.readFully(ch);
                    String id = new String(ch, 0, 4, "US-ASCII");
                    long len = le(ch, 4, 4);
                    long body = raf.getFilePointer();
                    if (id.equals("fmt ")) {
                        byte[] f = new byte[16];
                        raf.readFully(f);
                        format = (int) le(f, 0, 2);
                        channels = (int) le(f, 2, 2);
                        rate = (int) le(f, 4, 4);
                        bits = (int) le(f, 14, 2);
                    } else if (id.equals("data")) {
                        dataStart = body;
                        dataLen = Math.min(len, raf.length() - body);
                        break;
                    }
                    raf.seek(body + len + (len & 1));
                }
                if (format != 1 || bits != 16 || (channels != 1 && channels != 2) || rate < 8000 || rate > 48000 || dataStart < 0)
                    throw new IllegalArgumentException("need PCM16 mono/stereo 8-48 kHz; got format=" + format
                        + " ch=" + channels + " rate=" + rate + " bits=" + bits);
                int frameBytes = channels * 2;
                dataLen -= dataLen % frameBytes;
                if (dataLen <= 0) throw new IllegalArgumentException("empty audio");
                Class<?> cls = Class.forName("android.media.AudioTrack");
                int mask = channels == 1 ? 4 : 12;
                int min = (Integer) cls.getMethod("getMinBufferSize", int.class, int.class, int.class).invoke(null, rate, mask, 2);
                if (min <= 0) throw new IllegalStateException("min buffer=" + min);
                // STREAM_MUSIC (3), PCM_16BIT (2), MODE_STREAM (1); loudness follows the music stream volume.
                track = cls.getConstructor(int.class, int.class, int.class, int.class, int.class, int.class)
                    .newInstance(3, rate, mask, 2, Math.max(min, CHUNK * 4), 1);
                int state = (Integer) cls.getMethod("getState").invoke(track);
                if (state != 1) throw new IllegalStateException("track state=" + state);
                cls.getMethod("play").invoke(track);
                java.lang.reflect.Method write = cls.getMethod("write", byte[].class, int.class, int.class);
                raf.seek(dataStart);
                byte[] buf = new byte[CHUNK - CHUNK % frameBytes];
                long left = dataLen, written = 0;
                boolean cancelled = false;
                while (left > 0) {
                    if (stop.exists()) { cancelled = true; break; }
                    int n = raf.read(buf, 0, (int) Math.min(buf.length, left));
                    if (n <= 0) break;
                    int off = 0;
                    while (off < n) {
                        int w = (Integer) write.invoke(track, buf, off, n - off);
                        if (w < 0) throw new IllegalStateException("write=" + w);
                        off += w;
                    }
                    written += n;
                    left -= n;
                }
                long frames = written / frameBytes;
                if (cancelled) {
                    cls.getMethod("pause").invoke(track);
                    cls.getMethod("flush").invoke(track);
                    System.out.println("MAX_PLAY_CANCELLED written_frames=" + frames);
                    exit = 0;
                } else {
                    // Drain: wait for the playback head to reach the last written frame.
                    long deadline = System.currentTimeMillis() + frames * 1000L / rate + 3000L;
                    int head2 = 0;
                    while (System.currentTimeMillis() < deadline) {
                        if (stop.exists()) { cancelled = true; break; }
                        head2 = (Integer) cls.getMethod("getPlaybackHeadPosition").invoke(track);
                        if (head2 >= frames) break;
                        Thread.sleep(50);
                    }
                    if (cancelled) {
                        cls.getMethod("pause").invoke(track);
                        cls.getMethod("flush").invoke(track);
                        System.out.println("MAX_PLAY_CANCELLED written_frames=" + frames + " played_frames=" + head2);
                        exit = 0;
                    } else {
                        cls.getMethod("stop").invoke(track);
                        System.out.println("MAX_PLAY_RESULT written_frames=" + frames + " played_frames=" + head2
                            + " rate=" + rate + " channels=" + channels);
                        if (head2 <= 0) throw new IllegalStateException("no playback progress");
                        exit = 0;
                    }
                }
            } finally {
                raf.close();
            }
        } catch (Throwable error) {
            if (error instanceof java.lang.reflect.InvocationTargetException && error.getCause() != null) {
                error = error.getCause();
            }
            System.err.println("MAX_PLAY_ERROR " + error.getClass().getName() + ": " + error.getMessage());
        } finally {
            if (track != null) {
                try { track.getClass().getMethod("release").invoke(track); } catch (Throwable ignored) { }
            }
        }
        System.exit(exit);
    }

    private static long le(byte[] b, int off, int n) {
        long v = 0;
        for (int i = n - 1; i >= 0; i--) v = (v << 8) | (b[off + i] & 0xff);
        return v;
    }
}
