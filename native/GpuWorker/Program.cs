using System.Text;
using System.Text.Json;
using System.Runtime.InteropServices;
using Whisper.net;
using Whisper.net.LibraryLoader;
using Whisper.net.Logger;

Console.InputEncoding = Encoding.UTF8;
Console.OutputEncoding = new UTF8Encoding(false);
RuntimeOptions.RuntimeLibraryOrder = [RuntimeLibrary.Vulkan];
using var logger = LogProvider.AddLogger((level, message) => Console.Error.Write(message));
try
{
    var devices = GpuDevices.Read();
    if (args.Length == 1 && args[0] == "--list-devices")
    {
        Console.WriteLine(JsonSerializer.Serialize(devices));
        return 0;
    }
    if (args.Length != 2 || !int.TryParse(args[1], out var device) || device < 0 || device >= devices.Count)
        throw new InvalidOperationException("The selected Vulkan GPU is unavailable. Update the AMD/Intel graphics driver or select CPU.");
    using var factory = WhisperFactory.FromPath(args[0], new WhisperFactoryOptions
    {
        UseGpu = true,
        GpuDevice = device,
    });
    using var processor = factory.CreateBuilder()
        .WithLanguage("ru")
        .WithNoContext()
        .WithTokenTimestamps()
        .Build();
    Console.WriteLine(JsonSerializer.Serialize(new { type = "ready" }));
    while (Console.ReadLine() is string command)
    {
        using var request = JsonDocument.Parse(command);
        var path = request.RootElement.GetProperty("audio").GetString()!;
        using var stream = File.OpenRead(path);
        await foreach (var segment in processor.ProcessAsync(stream))
        {
            Console.WriteLine(JsonSerializer.Serialize(new
            {
                type = "segment", start = segment.Start.TotalSeconds,
                end = segment.End.TotalSeconds, text = segment.Text,
                tokens = segment.Tokens.Where(t => t.Id < 50257).Select(t => new
                {
                    text = t.Text, start = t.Start / 100.0, end = t.End / 100.0,
                }),
            }));
        }
        Console.WriteLine(JsonSerializer.Serialize(new { type = "done" }));
    }
    return 0;
}
catch (Exception exception)
{
    Console.Error.WriteLine(exception);
    return 1;
}

static class GpuDevices
{
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool SetDllDirectory(string path);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate int DeviceCount();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void DeviceDescription(int index, IntPtr description, nuint size);

    public static List<object> Read()
    {
        var path = Path.Combine(AppContext.BaseDirectory, "runtimes", "vulkan", "win-x64");
        SetDllDirectory(path);
        var library = NativeLibrary.Load(Path.Combine(path, "ggml-vulkan-whisper.dll"));
        var count = Marshal.GetDelegateForFunctionPointer<DeviceCount>(NativeLibrary.GetExport(library, "ggml_backend_vk_get_device_count"));
        var description = Marshal.GetDelegateForFunctionPointer<DeviceDescription>(NativeLibrary.GetExport(library, "ggml_backend_vk_get_device_description"));
        var result = new List<object>();
        var buffer = Marshal.AllocHGlobal(512);
        try
        {
            for (var i = 0; i < count(); i++)
            {
                description(i, buffer, 512);
                result.Add(new { index = i, name = Marshal.PtrToStringUTF8(buffer) ?? $"GPU {i}" });
            }
        }
        finally { Marshal.FreeHGlobal(buffer); }
        return result;
    }
}
