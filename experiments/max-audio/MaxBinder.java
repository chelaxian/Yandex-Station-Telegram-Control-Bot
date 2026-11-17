// Read-only Android 9 binder reachability check. It never plays sound.
public final class MaxBinder {
    public static void main(String[] args) {
        boolean found = false;
        try {
            Class<?> manager = Class.forName("android.os.ServiceManager");
            java.lang.reflect.Method get = manager.getMethod("getService", String.class);
            for (String name : new String[] {"audio", "media.audio_flinger", "media.player", "activity"}) {
                Object binder = get.invoke(null, name);
                System.out.println("MAX_BINDER " + name + "=" + (binder != null));
                found |= binder != null;
            }
        } catch (Throwable error) {
            if (error instanceof java.lang.reflect.InvocationTargetException && error.getCause() != null) {
                error = error.getCause();
            }
            System.out.println("MAX_BINDER_ERROR " + error.getClass().getName() + ": " + error.getMessage());
        }
        if (!found) System.exit(2);
    }
}
