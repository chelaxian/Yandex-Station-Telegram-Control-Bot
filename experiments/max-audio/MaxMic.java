// Standalone Android 9 microphone level probe. Audio stays in memory; only numeric levels are printed.
public final class MaxMic {
    public static void main(String[] args) {
        Object record = null;
        boolean ok = false;
        try {
            int source = args.length > 0 ? Integer.parseInt(args[0]) : 1;
            int rate = args.length > 1 ? Integer.parseInt(args[1]) : 16000;
            int seconds = args.length > 2 ? Integer.parseInt(args[2]) : 2;
            if ((source != 1 && source != 6) || (rate != 16000 && rate != 48000) || seconds < 1 || seconds > 3) {
                throw new IllegalArgumentException("parameters out of range");
            }
            Class<?> cls = Class.forName("android.media.AudioRecord");
            // Android 9 AudioRecord passes ActivityThread.currentOpPackageName() to native code; a bare
            // app_process has none and native String16(nullptr) crashes. Create the system context first.
            Class<?> thread = Class.forName("android.app.ActivityThread");
            try {
                Class.forName("android.os.Looper").getMethod("prepareMainLooper").invoke(null);
            } catch (Throwable ignored) { }
            thread.getMethod("systemMain").invoke(null);
            String opPackage = (String) thread.getMethod("currentOpPackageName").invoke(null);
            System.out.println("MAX_MIC_STAGE opPackage=" + (opPackage == null ? "null" : opPackage));
            if (opPackage == null || opPackage.isEmpty()) throw new IllegalStateException("no op package");
            // CHANNEL_IN_MONO=16, ENCODING_PCM_16BIT=2.
            int min = (Integer) cls.getMethod("getMinBufferSize", int.class, int.class, int.class).invoke(null, rate, 16, 2);
            if (min <= 0) throw new IllegalStateException("min buffer=" + min);
            int frames = rate * seconds;
            record = cls.getConstructor(int.class, int.class, int.class, int.class, int.class)
                .newInstance(source, rate, 16, 2, Math.max(min * 2, 8192));
            int state = (Integer) cls.getMethod("getState").invoke(record);
            if (state != 1) throw new IllegalStateException("record state=" + state);
            cls.getMethod("startRecording").invoke(record);
            short[] buffer = new short[4096];
            long total = 0, nonzero = 0, peak = 0;
            double sum = 0;
            java.lang.reflect.Method read = cls.getMethod("read", short[].class, int.class, int.class);
            long deadline = System.currentTimeMillis() + seconds * 1000L + 1500L;
            while (total < frames && System.currentTimeMillis() < deadline) {
                int n = (Integer) read.invoke(record, buffer, 0, buffer.length);
                if (n < 0) throw new IllegalStateException("read=" + n);
                for (int i = 0; i < n; i++) {
                    int value = Math.abs((int) buffer[i]);
                    if (value != 0) nonzero++;
                    if (value > peak) peak = value;
                    sum += (double) value * value;
                }
                total += n;
            }
            double rms = total == 0 ? 0 : Math.sqrt(sum / total);
            System.out.println("MAX_MIC_RESULT source=" + source + " rate=" + rate + " frames=" + total
                + " nonzero=" + nonzero + " peak=" + peak + " rms=" + String.format(java.util.Locale.US, "%.1f", rms));
            if (total < frames / 2) throw new IllegalStateException("too few frames");
            ok = true;
        } catch (Throwable error) {
            if (error instanceof java.lang.reflect.InvocationTargetException && error.getCause() != null) {
                error = error.getCause();
            }
            System.err.println("MAX_MIC_ERROR " + error.getClass().getName() + ": " + error.getMessage());
        } finally {
            if (record != null) {
                try { record.getClass().getMethod("stop").invoke(record); } catch (Throwable ignored) { }
                try { record.getClass().getMethod("release").invoke(record); } catch (Throwable ignored) { }
            }
        }
        System.exit(ok ? 0 : 1);
    }
}
