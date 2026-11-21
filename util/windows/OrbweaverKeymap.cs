// Copyright 2026 QMK
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Windows tray launcher for util/razer_orbweaver_editor.py: starts the editor
// without a console window, opens it in the browser, and stops it (with every
// build or flash it started) from the tray icon. Built with the C# compiler
// that ships with the .NET Framework (util/windows/build.ps1), so nothing has
// to be downloaded. Settings live in OrbweaverKeymap.ini next to the .exe.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("Orbweaver Keymap")]
[assembly: AssemblyDescription("Keymap editor for the Razer Orbweaver running QMK")]
[assembly: AssemblyProduct("Orbweaver Keymap")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

static class Program
{
    public const string AppName = "Orbweaver Keymap";

    public static bool NoBrowser;

    [STAThread]
    static void Main(string[] args)
    {
        NoBrowser = Array.IndexOf(args, "/nobrowser") >= 0;  // for testing
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Settings cfg;
        try { cfg = Settings.Load(); }
        catch (Exception e) { MessageBox.Show(e.Message, AppName, MessageBoxButtons.OK, MessageBoxIcon.Error); return; }

        bool first;
        using (var mutex = new Mutex(true, "Local\\OrbweaverKeymapEditor", out first))
        {
            if (!first || Editor.IsUp(cfg.Url, 1500))
            {
                // already running (from this launcher or by hand): just show it
                Editor.OpenBrowser(cfg.Url);
                return;
            }
            Application.Run(new Tray(cfg));
        }
    }
}

class Settings
{
    public string Repo, Python, PythonArgs = "", Keymap = "mine", LogFile;
    public int Port = 8765;
    public string Url { get { return "http://127.0.0.1:" + Port + "/"; } }
    public string EditorScript { get { return Path.Combine(Repo, "util", "razer_orbweaver_editor.py"); } }

    public static Settings Load()
    {
        var s = new Settings();
        string exeDir = AppDomain.CurrentDomain.BaseDirectory;
        string ini = Path.Combine(exeDir, "OrbweaverKeymap.ini");
        var kv = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        if (File.Exists(ini))
        {
            foreach (string raw in File.ReadAllLines(ini))
            {
                string line = raw.Trim();
                if (line.Length == 0 || line.StartsWith(";") || line.StartsWith("#") || line.StartsWith("[")) continue;
                int eq = line.IndexOf('=');
                if (eq > 0) kv[line.Substring(0, eq).Trim()] = line.Substring(eq + 1).Trim();
            }
        }
        string v;
        if (kv.TryGetValue("repo", out v) && v.Length > 0) s.Repo = Environment.ExpandEnvironmentVariables(v);
        else
        {
            // run from inside the repository (util\windows\): use it
            var d = new DirectoryInfo(exeDir);
            while (d != null && !File.Exists(Path.Combine(d.FullName, "util", "razer_orbweaver_editor.py"))) d = d.Parent;
            if (d != null) s.Repo = d.FullName;
        }
        if (s.Repo == null || !File.Exists(s.EditorScript))
            throw new Exception("Can't find the QMK repository with util\\razer_orbweaver_editor.py.\n\n" +
                                "Set repo= in " + ini + " to the qmk_firmware folder.");
        if (kv.TryGetValue("keymap", out v) && v.Length > 0) s.Keymap = v;
        if (kv.TryGetValue("port", out v)) int.TryParse(v, out s.Port);
        if (kv.TryGetValue("python", out v) && v.Length > 0) s.Python = Environment.ExpandEnvironmentVariables(v);
        else FindPython(s);
        if (s.Python == null || !File.Exists(s.Python))
            throw new Exception("Can't find Python 3. Install it from python.org (with the \"py\" launcher), " +
                                "or set python= in " + ini + " to python.exe.");
        string logDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), Program.AppName);
        Directory.CreateDirectory(logDir);
        s.LogFile = Path.Combine(logDir, "editor.log");
        return s;
    }

    static void FindPython(Settings s)
    {
        string win = Environment.GetFolderPath(Environment.SpecialFolder.Windows);
        string py = Path.Combine(win, "py.exe");
        if (File.Exists(py)) { s.Python = py; s.PythonArgs = "-3 "; return; }
        foreach (string dir in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(';'))
        {
            if (dir.Length == 0 || dir.IndexOf("WindowsApps", StringComparison.OrdinalIgnoreCase) >= 0) continue;  // Store alias stubs
            foreach (string name in new[] { "py.exe", "python.exe" })
            {
                string p = Path.Combine(dir.Trim(), name);
                if (File.Exists(p)) { s.Python = p; s.PythonArgs = name == "py.exe" ? "-3 " : ""; return; }
            }
        }
        string progs = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Python");
        if (Directory.Exists(progs))
        {
            var dirs = Directory.GetDirectories(progs, "Python3*");
            Array.Sort(dirs);
            for (int i = dirs.Length - 1; i >= 0; i--)
            {
                string p = Path.Combine(dirs[i], "python.exe");
                if (File.Exists(p)) { s.Python = p; return; }
            }
        }
    }
}

static class Editor
{
    public static string Get(string url, int timeoutMs)
    {
        try
        {
            var req = (HttpWebRequest)WebRequest.Create(url);
            req.Timeout = timeoutMs;
            req.Proxy = null;
            using (var resp = (HttpWebResponse)req.GetResponse())
            using (var r = new StreamReader(resp.GetResponseStream()))
                return r.ReadToEnd();
        }
        catch (Exception) { return null; }
    }

    public static bool IsUp(string url, int timeoutMs) { return Get(url + "api/state", timeoutMs) != null; }

    public static bool JobRunning(string url)
    {
        string j = Get(url + "api/job?since=999999", 1500);
        return j != null && j.Replace(" ", "").Contains("\"state\":\"running\"");
    }

    public static void OpenBrowser(string url)
    {
        if (Program.NoBrowser) return;
        try { Process.Start(new ProcessStartInfo(url) { UseShellExecute = true }); } catch (Exception) { }
    }

    /// The real python.exe behind the py launcher, so the editor is a direct
    /// child that can be put in the job object before it starts anything.
    public static string ResolveInterpreter(Settings cfg)
    {
        if (!Path.GetFileName(cfg.Python).Equals("py.exe", StringComparison.OrdinalIgnoreCase)) return cfg.Python;
        try
        {
            var psi = new ProcessStartInfo(cfg.Python, cfg.PythonArgs + "-c \"import sys; print(sys.executable)\"")
            { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true };
            using (var p = Process.Start(psi))
            {
                string exe = p.StandardOutput.ReadToEnd().Trim();
                p.WaitForExit(15000);
                if (p.ExitCode == 0 && File.Exists(exe)) { cfg.PythonArgs = ""; return exe; }
            }
        }
        catch (Exception) { }
        return cfg.Python;
    }
}

/// A Windows job object with "kill on close": the editor and everything it
/// starts (docker, the flasher) end when the launcher ends, however it ends.
static class KillJob
{
    [StructLayout(LayoutKind.Sequential)]
    struct BasicLimits
    {
        public long PerProcessUserTimeLimit, PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass, SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct IoCounters { public ulong a, b, c, d, e, f; }

    [StructLayout(LayoutKind.Sequential)]
    struct ExtendedLimits
    {
        public BasicLimits Basic;
        public IoCounters Io;
        public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern IntPtr CreateJobObject(IntPtr attributes, string name);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool SetInformationJobObject(IntPtr job, int infoClass, ref ExtendedLimits info, uint length);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool CloseHandle(IntPtr handle);

    static IntPtr job = IntPtr.Zero;

    public static void Add(Process p)
    {
        if (job == IntPtr.Zero)
        {
            job = CreateJobObject(IntPtr.Zero, null);
            var info = new ExtendedLimits();
            info.Basic.LimitFlags = 0x2000;  // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            SetInformationJobObject(job, 9 /* JobObjectExtendedLimitInformation */, ref info, (uint)Marshal.SizeOf(typeof(ExtendedLimits)));
        }
        AssignProcessToJobObject(job, p.Handle);
    }

    /// Ends every process in the job now.
    public static void KillAll()
    {
        if (job != IntPtr.Zero) { CloseHandle(job); job = IntPtr.Zero; }
    }
}

class Tray : ApplicationContext
{
    readonly Settings cfg;
    readonly NotifyIcon icon;
    readonly Control ui = new Control();
    Process proc;
    StreamWriter log;
    bool quitting;

    public Tray(Settings cfg)
    {
        this.cfg = cfg;
        IntPtr handle = ui.Handle;  // create the window handle now, for BeginInvoke from other threads

        var menu = new ContextMenuStrip();
        var open = menu.Items.Add("Open keymap editor", null, delegate { Editor.OpenBrowser(cfg.Url); });
        open.Font = new Font(open.Font, FontStyle.Bold);
        menu.Items.Add("Show log", null, delegate { ShowLog(); });
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Quit", null, delegate { Quit(); });

        icon = new NotifyIcon();
        icon.Icon = LoadIcon();
        icon.Text = Program.AppName + " (starting)";
        icon.ContextMenuStrip = menu;
        icon.DoubleClick += delegate { Editor.OpenBrowser(cfg.Url); };
        icon.Visible = true;

        Start();
    }

    static Icon LoadIcon()
    {
        var s = Assembly.GetExecutingAssembly().GetManifestResourceStream("orbweaver_keymap.ico");
        return s != null ? new Icon(s) : SystemIcons.Application;
    }

    void Start()
    {
        // shared, so "Show log" can open it while the editor writes to it
        log = new StreamWriter(new FileStream(cfg.LogFile, FileMode.Create, FileAccess.Write, FileShare.ReadWrite)) { AutoFlush = true };
        string python = Editor.ResolveInterpreter(cfg);
        log.WriteLine(DateTime.Now + "  starting " + python + " " + cfg.EditorScript);
        var psi = new ProcessStartInfo(python,
            cfg.PythonArgs + "-u \"" + cfg.EditorScript + "\" --no-browser --port " + cfg.Port + " --keymap " + cfg.Keymap);
        psi.WorkingDirectory = cfg.Repo;
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        psi.RedirectStandardOutput = true;
        psi.RedirectStandardError = true;
        psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
        proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
        DataReceivedEventHandler sink = delegate (object o, DataReceivedEventArgs e)
        {
            if (e.Data == null) return;
            try { lock (log) log.WriteLine(e.Data); } catch (Exception) { }  // late output after quitting
        };
        proc.OutputDataReceived += sink;
        proc.ErrorDataReceived += sink;
        proc.Exited += delegate
        {
            if (quitting) return;
            try { ui.BeginInvoke((MethodInvoker)EditorExited); } catch (Exception) { }
        };
        try
        {
            proc.Start();
            KillJob.Add(proc);
            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();
        }
        catch (Exception e)
        {
            MessageBox.Show("Could not start Python:\n" + e.Message, Program.AppName, MessageBoxButtons.OK, MessageBoxIcon.Error);
            ExitNow();
            return;
        }
        new Thread(WaitUntilReady) { IsBackground = true }.Start();
    }

    void WaitUntilReady()
    {
        for (int i = 0; i < 100 && !quitting; i++)
        {
            if (proc.HasExited) return;  // EditorExited reports it
            if (Editor.IsUp(cfg.Url, 1000))
            {
                ui.BeginInvoke((MethodInvoker)delegate
                {
                    icon.Text = Program.AppName + " (running)";
                    Editor.OpenBrowser(cfg.Url);
                    icon.ShowBalloonTip(4000, Program.AppName, "The editor is open in your browser. Right-click this icon to open it again or quit.", ToolTipIcon.Info);
                });
                return;
            }
            Thread.Sleep(200);
        }
    }

    void EditorExited()
    {
        if (quitting) return;
        string tail = "";
        try
        {
            proc.WaitForExit();  // lets the output readers finish
            lock (log) log.Flush();
            using (var fs = new FileStream(cfg.LogFile, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            using (var r = new StreamReader(fs))
            {
                string all = r.ReadToEnd();
                tail = all.Length > 1500 ? all.Substring(all.Length - 1500) : all;
            }
        }
        catch (Exception) { }
        MessageBox.Show("The editor stopped (exit code " + proc.ExitCode + ").\n\n" + tail, Program.AppName,
                        MessageBoxButtons.OK, MessageBoxIcon.Warning);
        ExitNow();
    }

    void ShowLog()
    {
        try { Process.Start(new ProcessStartInfo("notepad.exe", "\"" + cfg.LogFile + "\"") { UseShellExecute = true }); } catch (Exception) { }
    }

    void Quit()
    {
        if (Editor.JobRunning(cfg.Url) &&
            MessageBox.Show("A build or flash is still running. Quit anyway?\n\nIf the keypad is in its bootloader, it stays there until you flash it again (or run the flasher with --exit).",
                            Program.AppName, MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes)
            return;
        quitting = true;
        KillJob.KillAll();  // the editor and everything it started (docker, the flasher)
        try { if (proc != null) proc.WaitForExit(5000); } catch (Exception) { }
        ExitNow();
    }

    void ExitNow()
    {
        icon.Visible = false;
        icon.Dispose();
        if (log != null) try { log.Close(); } catch (Exception) { }
        ExitThread();
    }
}
