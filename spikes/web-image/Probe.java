import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/** What an embedded database needs from the platform. One line per capability; a failure does not stop the rest. */
public class Probe {
  interface Check { String run() throws Throwable; }

  static void check(String name, Check c) {
    System.out.println("START " + name);
    try {
      System.out.println("PASS " + name + ": " + c.run());
    } catch (Throwable e) {
      System.out.println("FAIL " + name + ": " + e);
    }
  }

  static void require(boolean ok, String what) {
    if (!ok) throw new AssertionError(what);
  }

  public static void main(String[] args) {
    System.out.println("java=" + System.getProperty("java.version"));
    check("files", () -> {
      Path dir = Files.createTempDirectory("probe");
      Path f = dir.resolve("a.txt");
      Files.writeString(f, "water pump");
      require(Files.readString(f).equals("water pump"), "read differs");
      return "wrote and read back in " + dir;
    });
    check("random-access-file", () -> {
      Path f = Files.createTempFile("probe", ".raf");
      try (RandomAccessFile r = new RandomAccessFile(f.toFile(), "rw")) {
        r.seek(65536);
        r.writeLong(42);
        r.seek(65536);
        require(r.readLong() == 42, "read differs");
        return "length=" + r.length();
      }
    });
    check("file-channel", () -> {
      Path f = Files.createTempFile("probe", ".ch");
      try (FileChannel c = FileChannel.open(f, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
        ByteBuffer b = ByteBuffer.allocateDirect(8).putLong(0, 7);
        c.write(b, 4096);
        c.force(true);
        ByteBuffer in = ByteBuffer.allocate(8);
        c.read(in, 4096);
        require(in.getLong(0) == 7, "read differs");
        return "positional write, force, read";
      }
    });
    check("file-lock", () -> {
      Path f = Files.createTempFile("probe", ".lck");
      try (FileChannel c = FileChannel.open(f, StandardOpenOption.WRITE); FileLock l = c.tryLock()) {
        require(l != null, "no lock");
        return "locked";
      }
    });
    check("memory-mapped-file", () -> {
      Path f = Files.createTempFile("probe", ".map");
      try (FileChannel c = FileChannel.open(f, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
        MappedByteBuffer m = c.map(FileChannel.MapMode.READ_WRITE, 0, 4096);
        m.putInt(0, 5);
        require(m.getInt(0) == 5, "read differs");
        return "mapped";
      }
    });
    check("thread-start-join", () -> {
      AtomicInteger n = new AtomicInteger();
      Thread t = new Thread(() -> n.set(1));
      t.start();
      t.join(5000);
      require(n.get() == 1, "thread did not run");
      return "ran";
    });
    check("background-thread-with-wait-notify", () -> {
      Object lock = new Object();
      boolean[] done = {false};
      Thread t = new Thread(() -> {
        synchronized (lock) { done[0] = true; lock.notifyAll(); }
      });
      t.setDaemon(true);
      synchronized (lock) {
        t.start();
        long end = System.currentTimeMillis() + 5000;
        while (!done[0] && System.currentTimeMillis() < end) lock.wait(100);
      }
      require(done[0], "never notified");
      return "notified";
    });
    check("scheduled-executor", () -> {
      ScheduledExecutorService s = Executors.newScheduledThreadPool(1);
      try {
        return "got " + s.schedule(() -> 3, 10, TimeUnit.MILLISECONDS).get(5, TimeUnit.SECONDS);
      } finally {
        s.shutdownNow();
      }
    });
    check("completable-future", () -> "got " + CompletableFuture.supplyAsync(() -> 9).get(5, TimeUnit.SECONDS));
    System.out.println("PROBE finished");
  }
}
