using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

[assembly:System.Reflection.AssemblyTitle("Sahara GIS")]
[assembly:System.Reflection.AssemblyVersion("1.5.0.0")]

internal static class Program {
    internal static readonly string Root=AppDomain.CurrentDomain.BaseDirectory;
    internal static readonly string Data=Path.Combine(Root,"data");
    internal static readonly JavaScriptSerializer Json=new JavaScriptSerializer();
    internal static string Url, Instance, ReadyFile;
    internal static Process Server, Desktop;
    internal static IntPtr Job=IntPtr.Zero;
    static readonly object LogLock=new object();
    static Mutex InstanceMutex;
    static EventWaitHandle StopEvent;
    static bool Stopped;

    [STAThread]
    static int Main(string[] args) {
        bool smoke=Array.IndexOf(args,"--self-test")>=0;
        try {
            Directory.CreateDirectory(Data);
            string id=BitConverter.ToString(SHA256.Create().ComputeHash(Encoding.UTF8.GetBytes(Path.GetFullPath(Root).ToLowerInvariant()))).Replace("-","").Substring(0,20);
            if(Array.IndexOf(args,"--stop")>=0) {
                try {using(var e=EventWaitHandle.OpenExisting("Local\\SASPlanetStop_"+id))e.Set();} catch(WaitHandleCannotBeOpenedException){}
                return 0;
            }
            if(smoke) {
                try { StartServer(true); SelfTest(); return 0; }
                finally {StopServer();}
            }
            bool created;
            InstanceMutex=new Mutex(true,"Local\\SASPlanet_"+id,out created);
            if(!created) { OpenExisting(); InstanceMutex.Dispose(); return 0; }
            StopEvent=new EventWaitHandle(false,EventResetMode.AutoReset,"Local\\SASPlanetStop_"+id);
            Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
            Application.ApplicationExit+=delegate{StopServer();};
            Application.Run(new Controller(Array.IndexOf(args,"--no-browser")<0));
            StopEvent.Dispose();InstanceMutex.ReleaseMutex();InstanceMutex.Dispose();return 0;
        } catch(Exception error) {
            Log(error.ToString());StopServer();
            if(!smoke)MessageBox.Show("تعذر تشغيل البرنامج. فك ضغط الحزمة بالكامل في مجلد قابل للكتابة.\n\n"+error.Message+"\n\nراجع data/launcher.log", "Sahara GIS",MessageBoxButtons.OK,MessageBoxIcon.Error);
            return 1;
        }
    }
    internal static void Log(string message) { try {lock(LogLock)File.AppendAllText(Path.Combine(Data,"launcher.log"),DateTime.Now.ToString("s")+" "+message+Environment.NewLine,Encoding.UTF8);}catch{} }
    static string Quote(string value) {return "\""+value.Replace("\"","\\\"")+"\"";}
    static int FreePort() {var listener=new TcpListener(IPAddress.Loopback,0);listener.Start();int p=((IPEndPoint)listener.LocalEndpoint).Port;listener.Stop();return p;}
    static bool Available(int port) {try {var l=new TcpListener(IPAddress.Loopback,port);l.Start();l.Stop();return true;}catch(SocketException){return false;}}
    internal static void StartServer(bool smoke) {
        string app=Path.Combine(Root,"app"), node=Path.Combine(Root,"runtime","node","node.exe"),python=Path.Combine(Root,"runtime","python","python.exe");
        foreach(string f in new[]{node,python,Path.Combine(app,"server.mjs"),Path.Combine(app,"dist","index.html")})if(!File.Exists(f))throw new FileNotFoundException("ملفات البرنامج ناقصة. فك ضغط ملف ZIP كاملاً.",f);
        string probe=Path.Combine(Data,".write-test");File.WriteAllText(probe,"ok");File.Delete(probe);
        int port=38765, stored;string portFile=Path.Combine(Data,"port.txt");
        if(!smoke&&File.Exists(portFile)&&Int32.TryParse(File.ReadAllText(portFile),out stored)&&stored>1024&&stored<65536)port=stored;
        if(smoke||!Available(port))port=FreePort();
        if(!smoke)File.WriteAllText(portFile,port.ToString());
        Instance=Guid.NewGuid().ToString("N");ReadyFile=Path.Combine(Data,smoke?"self-test-session.json":"session.json");
        if(File.Exists(ReadyFile))File.Delete(ReadyFile);
        var info=new ProcessStartInfo(node,Quote(Path.Combine(app,"server.mjs")));
        info.WorkingDirectory=app;info.UseShellExecute=false;info.CreateNoWindow=true;info.WindowStyle=ProcessWindowStyle.Hidden;info.RedirectStandardOutput=true;info.RedirectStandardError=true;
        foreach(string key in new[]{"NODE_OPTIONS","NODE_PATH","PYTHONHOME","PYTHONPATH","PYTHONSTARTUP","PROJ_LIB","PROJ_DATA","GDAL_DATA"})info.EnvironmentVariables.Remove(key);
        info.EnvironmentVariables["NODE_ENV"]="production";info.EnvironmentVariables["HOST"]="127.0.0.1";info.EnvironmentVariables["PORT"]=port.ToString();
        info.EnvironmentVariables["SAS_PORTABLE"]="1";info.EnvironmentVariables["SAS_PYTHON"]=python;info.EnvironmentVariables["SAS_READY_FILE"]=ReadyFile;info.EnvironmentVariables["SAS_INSTANCE_ID"]=Instance;
        info.EnvironmentVariables["PYTHONIOENCODING"]="utf-8";info.EnvironmentVariables["PYTHONUTF8"]="1";
        Server=new Process();Server.StartInfo=info;Server.OutputDataReceived+=delegate(object s,DataReceivedEventArgs e){if(e.Data!=null)Log(e.Data);};Server.ErrorDataReceived+=delegate(object s,DataReceivedEventArgs e){if(e.Data!=null)Log(e.Data);};
        Server.Start();AttachJob(Server);Server.BeginOutputReadLine();Server.BeginErrorReadLine();
        DateTime deadline=DateTime.UtcNow.AddSeconds(40);
        while(DateTime.UtcNow<deadline) {
            if(Server.HasExited)throw new Exception("توقف التشغيل. راجع data/launcher.log.");
            if(File.Exists(ReadyFile))try {
                var state=Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(ReadyFile));
                string address=Convert.ToString(state["url"]);Uri uri;
                if(Convert.ToString(state["instance"])==Instance&&Uri.TryCreate(address,UriKind.Absolute,out uri)&&uri.Host=="127.0.0.1"&&uri.Port==port){Url=address;return;}
            }catch(IOException){}catch(ArgumentException){}
            Thread.Sleep(100);
        }
        throw new TimeoutException("استغرق بدء البرنامج وقتاً طويلاً. راجع data/launcher.log.");
    }
    static WebClient Client(){var client=new WebClient();client.Proxy=null;client.Encoding=Encoding.UTF8;return client;}
    static void SelfTest() {
        Dictionary<string,object> health,sources,result;
        using(var client=Client()) {
            health=Json.Deserialize<Dictionary<string,object>>(client.DownloadString(Url+"api/health"));
            if(!Convert.ToBoolean(health["portable"])||Convert.ToString(health["instance"])!=Instance)throw new Exception("Portable server health check failed.");
            var cache=Json.Deserialize<Dictionary<string,object>>(client.DownloadString(Url+"api/cache/stats"));
            if(!String.Equals(Path.GetFullPath(Convert.ToString(cache["base_dir"])),Path.GetFullPath(Path.Combine(Root,"cache_gmt")),StringComparison.OrdinalIgnoreCase)||Convert.ToString(cache["format"])!="gm1")throw new Exception("Portable cache_gmt path check failed.");
            sources=Json.Deserialize<Dictionary<string,object>>(client.DownloadString(Url+"api/sources"));
            if(!Convert.ToBoolean(sources["success"]))throw new Exception("Bundled Python source listing failed.");
            client.Headers[HttpRequestHeader.ContentType]="application/json";
            string code="import json,sys,sqlite3,ssl\nfrom PIL import Image\nfrom sas_planet_py.arcgis_export import geotiff\nfrom sas_planet_py.terrain_analysis import terrain_metrics\npayload=geotiff([[1.25,2],[3,None]],(3,35,4,36),'DEM','m')\nassert len(payload)>100\nassert terrain_metrics([[5]*3 for _ in range(3)],10,10)['slope'][1][1]==0\nprint(json.dumps({'python':sys.executable,'version':sys.version,'sqlite':sqlite3.sqlite_version,'geotiff':True}))";
            result=Json.Deserialize<Dictionary<string,object>>(client.UploadString(Url+"api/python/run",Json.Serialize(new {code=code})));
            if(!Convert.ToBoolean(result["success"]))throw new Exception("Bundled Python/Pillow/GeoTIFF check failed: "+Convert.ToString(result["stderr"]));
        }
        File.WriteAllText(Path.Combine(Data,"self-test.json"),Json.Serialize(new {success=true,health=health,python=Json.DeserializeObject(Convert.ToString(result["stdout"]).Trim()),jobObject=Job!=IntPtr.Zero}),Encoding.UTF8);
    }
    static void OpenExisting() {
        string path=Path.Combine(Data,"session.json");
        for(int n=0;n<100;n++){if(File.Exists(path)){try{var s=Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(path));Uri uri;if(Uri.TryCreate(Convert.ToString(s["url"]),UriKind.Absolute,out uri)&&uri.Host=="127.0.0.1"){Url=uri.AbsoluteUri;OpenBrowser();return;}}catch{}}Thread.Sleep(100);}
    }
    internal static void OpenBrowser() {
        if(String.IsNullOrEmpty(Url))return;
        if(Desktop!=null&&!Desktop.HasExited){Desktop.Refresh();ShowWindow(Desktop.MainWindowHandle,9);SetForegroundWindow(Desktop.MainWindowHandle);return;}
        string executable=Path.Combine(Root,"runtime","desktop","Sahara GIS.exe");
        if(!File.Exists(executable))throw new FileNotFoundException("محرك نافذة صحارى GIS غير موجود. فك ضغط الحزمة كاملة.",executable);
        try {using(var client=Client()){var health=Json.Deserialize<Dictionary<string,object>>(client.DownloadString(Url+"api/health"));if(!health.ContainsKey("desktopSupport")){MessageBox.Show("أغلق النسخة القديمة من أيقونتها بجانب الساعة ثم أعد تشغيل Sahara GIS.", "Sahara GIS");return;}}}catch(Exception error){MessageBox.Show(error.Message,"Sahara GIS");return;}
        Desktop=new Process();Desktop.StartInfo=new ProcessStartInfo(executable,"--root="+Quote(Root.TrimEnd(Path.DirectorySeparatorChar))+" --url="+Quote(Url)){WorkingDirectory=Root,UseShellExecute=false};
        foreach(string key in new[]{"ELECTRON_RUN_AS_NODE","NODE_OPTIONS","NODE_PATH"})Desktop.StartInfo.EnvironmentVariables.Remove(key);
        Desktop.EnableRaisingEvents=true;Desktop.Exited+=delegate{try{if(StopEvent!=null)StopEvent.Set();}catch{}};
        Desktop.Start();if(Job!=IntPtr.Zero)AssignProcessToJobObject(Job,Desktop.Handle);
    }
    [DllImport("user32.dll")]static extern bool SetForegroundWindow(IntPtr window);
    [DllImport("user32.dll")]static extern bool ShowWindow(IntPtr window,int command);
    internal static void StopServer() {
        if(Stopped)return;Stopped=true;
        if(Job!=IntPtr.Zero){CloseHandle(Job);Job=IntPtr.Zero;}
        if(Server!=null)try {if(!Server.HasExited){var kill=new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),"taskkill.exe"),"/PID "+Server.Id+" /T /F"){UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden};using(var process=Process.Start(kill))process.WaitForExit(4000);}Server.Dispose();}catch{}
        if(!String.IsNullOrEmpty(ReadyFile))try{File.Delete(ReadyFile);}catch{}
    }
    static void AttachJob(Process process) {
        Job=CreateJobObject(IntPtr.Zero,null);if(Job==IntPtr.Zero)return;
        var limit=new ExtendedLimits();limit.Basic.LimitFlags=0x2000;
        int size=Marshal.SizeOf(typeof(ExtendedLimits));IntPtr pointer=Marshal.AllocHGlobal(size);
        try{Marshal.StructureToPtr(limit,pointer,false);if(!SetInformationJobObject(Job,9,pointer,(uint)size)||!AssignProcessToJobObject(Job,process.Handle)){CloseHandle(Job);Job=IntPtr.Zero;}}
        finally{Marshal.FreeHGlobal(pointer);}
    }
    [StructLayout(LayoutKind.Sequential)]struct BasicLimits{public long ProcessTime,JobTime;public uint LimitFlags;public UIntPtr MinWorkingSet,MaxWorkingSet;public uint ActiveProcessLimit;public UIntPtr Affinity;public uint PriorityClass,SchedulingClass;}
    [StructLayout(LayoutKind.Sequential)]struct IoCounters{public ulong ReadOperations,WriteOperations,OtherOperations,ReadBytes,WriteBytes,OtherBytes;}
    [StructLayout(LayoutKind.Sequential)]struct ExtendedLimits{public BasicLimits Basic;public IoCounters Io;public UIntPtr ProcessMemory,JobMemory,PeakProcessMemory,PeakJobMemory;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr CreateJobObject(IntPtr attributes,string name);
    [DllImport("kernel32.dll")]static extern bool SetInformationJobObject(IntPtr job,int informationClass,IntPtr info,uint length);
    [DllImport("kernel32.dll")]static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
    [DllImport("kernel32.dll")]static extern bool CloseHandle(IntPtr handle);

    sealed class Controller:Form {
        readonly NotifyIcon tray=new NotifyIcon();readonly Label status=new Label();readonly System.Windows.Forms.Timer timer=new System.Windows.Forms.Timer();readonly bool openBrowser;
        internal Controller(bool open) {
            openBrowser=open;Text="Sahara GIS";Size=new Size(420,190);StartPosition=FormStartPosition.CenterScreen;FormBorderStyle=FormBorderStyle.FixedDialog;MaximizeBox=false;
            Icon=Icon.ExtractAssociatedIcon(Application.ExecutablePath);RightToLeft=RightToLeft.Yes;RightToLeftLayout=true;
            status.Text="جارٍ تشغيل البرنامج…";status.Dock=DockStyle.Top;status.Height=65;status.TextAlign=ContentAlignment.MiddleCenter;Controls.Add(status);
            var buttons=new FlowLayoutPanel{Dock=DockStyle.Bottom,Height=55,FlowDirection=FlowDirection.RightToLeft,Padding=new Padding(10)};
            foreach(var entry in new[]{new KeyValuePair<string,Action>("فتح البرنامج",OpenBrowser),new KeyValuePair<string,Action>("ملفات البرنامج",delegate{Process.Start(new ProcessStartInfo(Root){UseShellExecute=true});}),new KeyValuePair<string,Action>("إنهاء",delegate{Application.Exit();})}) {var button=new Button{Text=entry.Key,Width=115,Height=30};Action fn=entry.Value;button.Click+=delegate{fn();};buttons.Controls.Add(button);}Controls.Add(buttons);
            var menu=new ContextMenuStrip();menu.Items.Add("فتح البرنامج",null,delegate{OpenBrowser();});menu.Items.Add("لوحة التحكم",null,delegate{Show();Activate();});menu.Items.Add("إنهاء البرنامج",null,delegate{Application.Exit();});tray.Icon=Icon;tray.Text="Sahara GIS";tray.ContextMenuStrip=menu;tray.DoubleClick+=delegate{OpenBrowser();};tray.Visible=true;
            timer.Interval=500;timer.Tick+=delegate{if(StopEvent.WaitOne(0)){Application.Exit();return;}if(Server!=null&&Server.HasExited){status.Text="توقف البرنامج. راجع data/launcher.log";Show();timer.Stop();}};
            Shown+=delegate{ThreadPool.QueueUserWorkItem(delegate{try{StartServer(false);BeginInvoke((Action)delegate{status.Text="البرنامج يعمل. استخدم أيقونته بجانب الساعة للإغلاق.";timer.Start();if(openBrowser){OpenBrowser();Hide();}});}catch(Exception e){Log(e.ToString());BeginInvoke((Action)delegate{MessageBox.Show(e.Message,Text);Application.Exit();});}});};
            FormClosed+=delegate{timer.Stop();tray.Visible=false;tray.Dispose();};
        }
    }
}
