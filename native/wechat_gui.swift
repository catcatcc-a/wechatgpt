import AppKit
import ApplicationServices
import Vision
import Foundation

struct GUIError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}
let bundleID = "com.tencent.xinWeChat"
func fail(_ message: String) throws -> Never { throw GUIError(message: message) }
func application() throws -> NSRunningApplication {
    guard AXIsProcessTrusted() else { try fail("Accessibility permission is required for the MCP host application.") }
    guard let app = NSRunningApplication.runningApplications(withBundleIdentifier: bundleID).first else {
        try fail("WeChat is not running. Open WeChat and log in first.")
    }
    return app
}
func activate(_ app: NSRunningApplication) throws {
    let opener = Process(); opener.executableURL = URL(fileURLWithPath: "/usr/bin/open")
    opener.arguments = ["-b", bundleID]
    try opener.run(); opener.waitUntilExit()
    RunLoop.current.run(until: Date().addingTimeInterval(0.35))
    if NSWorkspace.shared.frontmostApplication?.bundleIdentifier != bundleID {
        app.activate(options: [.activateAllWindows])
        for _ in 0..<30 { RunLoop.current.run(until: Date().addingTimeInterval(0.1)); if NSWorkspace.shared.frontmostApplication?.bundleIdentifier == bundleID { break } }
    }
    guard NSWorkspace.shared.frontmostApplication?.bundleIdentifier == bundleID else { try fail("WeChat could not become the active application.") }
}
func window(_ app: NSRunningApplication) throws -> [String:Any] {
    let options: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
    let all = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String:Any]] ?? []
    let candidates = all.filter {
        ($0[kCGWindowOwnerPID as String] as? Int) == Int(app.processIdentifier)
        && ($0[kCGWindowLayer as String] as? Int) == 0
        && (($0[kCGWindowBounds as String] as? [String:Double])?["Width"] ?? 0) > 200
        && (($0[kCGWindowBounds as String] as? [String:Double])?["Height"] ?? 0) > 200
    }
    guard let win = candidates.first else { try fail("No visible WeChat window. Open the chat window first.") }
    return win
}
func runTask(_ executable: String, _ arguments: [String]) throws {
    let task = Process(); task.executableURL = URL(fileURLWithPath: executable); task.arguments = arguments
    task.standardOutput = FileHandle.nullDevice
    let err = Pipe(); task.standardError = err
    try task.run(); task.waitUntilExit()
    if task.terminationStatus != 0 { try fail("Screen capture failed; enable Screen Recording for the MCP host.") }
}
func snapshot(_ app: NSRunningApplication, directory: String, activateWindow: Bool = true) throws -> [String:Any] {
    if activateWindow { try activate(app) }
    let win = try window(app)
    let id = win[kCGWindowNumber as String] as! UInt32
    let rect = win[kCGWindowBounds as String] as! [String:Double]
    let dir = URL(fileURLWithPath: directory, isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
    let path = dir.appendingPathComponent("wechat-\(UUID().uuidString).png").path
    if activateWindow {
        // WeChat renders search results in a separate popup window. Capturing
        // only the main window omits it even when it is visible on screen.
        let region = [rect["X"]!, rect["Y"]!, rect["Width"]!, rect["Height"]!].map { String(Int($0)) }.joined(separator: ",")
        try runTask("/usr/sbin/screencapture", ["-x", "-R", region, path])
        guard NSWorkspace.shared.frontmostApplication?.bundleIdentifier == bundleID else { try fail("WeChat lost focus during capture; action cancelled.") }
    } else {
        try runTask("/usr/sbin/screencapture", ["-x", "-o", "-l", String(id), path])
    }
    try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: path)
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = false
    try VNImageRequestHandler(url: URL(fileURLWithPath: path)).perform([request])
    let width = rect["Width"]!, height = rect["Height"]!
    let tokens: [[String:Any]] = (request.results ?? []).compactMap { observation in
        guard let text = observation.topCandidates(1).first else { return nil }
        let b = observation.boundingBox
        return ["text": text.string, "confidence": text.confidence,
                "x": b.minX * width, "y": (1 - b.maxY) * height,
                "width": b.width * width, "height": b.height * height]
    }.sorted { ($0["y"] as! Double) < ($1["y"] as! Double) }
    return ["window_id": id, "window": rect, "screenshot": path, "tokens": tokens,
            "source": "macOS Vision OCR", "pid": app.processIdentifier]
}
func verifyWindow(_ args: [String:Any], _ app: NSRunningApplication) throws -> [String:Double] {
    guard NSWorkspace.shared.frontmostApplication?.bundleIdentifier == bundleID else { try fail("WeChat lost focus; action cancelled.") }
    let win = try window(app)
    guard let expectedID = args["window_id"] as? Int,
          (win[kCGWindowNumber as String] as? Int) == expectedID,
          let expected = args["window"] as? [String:Double],
          let actual = win[kCGWindowBounds as String] as? [String:Double],
          ["X", "Y", "Width", "Height"].allSatisfy({ abs((expected[$0] ?? -10000) - (actual[$0] ?? 10000)) < 1 }) else {
        try fail("WeChat window changed since the screenshot; action cancelled.")
    }
    return actual
}
func press(_ key: CGKeyCode, flags: CGEventFlags = []) {
    for down in [true, false] {
        let e = CGEvent(keyboardEventSource: nil, virtualKey: key, keyDown: down)
        e?.flags = flags; e?.post(tap: .cghidEventTap)
    }
}
func click(_ point: CGPoint, right: Bool = false) {
    let button: CGMouseButton = right ? .right : .left
    let down: CGEventType = right ? .rightMouseDown : .leftMouseDown
    let up: CGEventType = right ? .rightMouseUp : .leftMouseUp
    CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: point, mouseButton: button)?.post(tap: .cghidEventTap)
    CGEvent(mouseEventSource: nil, mouseType: down, mouseCursorPosition: point, mouseButton: button)?.post(tap: .cghidEventTap)
    CGEvent(mouseEventSource: nil, mouseType: up, mouseCursorPosition: point, mouseButton: button)?.post(tap: .cghidEventTap)
}
func withClipboard<T>(_ body: (NSPasteboard) throws -> T) rethrows -> T {
    let board = NSPasteboard.general
    let saved = (board.pasteboardItems ?? []).map { item in
        item.types.compactMap { type -> (NSPasteboard.PasteboardType, Data)? in
            guard let data = item.data(forType: type) else { return nil }; return (type, data)
        }
    }
    defer {
        board.clearContents()
        let restored = saved.map { parts -> NSPasteboardItem in
            let item = NSPasteboardItem(); for (type,data) in parts { item.setData(data, forType: type) }; return item
        }
        if !restored.isEmpty { board.writeObjects(restored) }
    }
    return try body(board)
}
func run(_ args: [String:Any]) throws -> [String:Any] {
    let action = args["action"] as? String ?? "snapshot"
    if action == "focus_info" {
        return ["bundle_id": NSWorkspace.shared.frontmostApplication?.bundleIdentifier ?? ""]
    }
    if action == "restore_focus" {
        guard NSWorkspace.shared.frontmostApplication?.bundleIdentifier == bundleID,
              let previous = args["bundle_id"] as? String, previous != bundleID,
              let app = NSRunningApplication.runningApplications(withBundleIdentifier: previous).first else {
            return ["restored": false]
        }
        return ["restored": app.activate(options: [])]
    }
    if action == "status" {
        let installed = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bundleID)
        let info = installed.flatMap { Bundle(url: $0)?.infoDictionary }
        return ["accessibility": AXIsProcessTrusted(), "screen_capture": CGPreflightScreenCaptureAccess(),
                "running": !NSRunningApplication.runningApplications(withBundleIdentifier: bundleID).isEmpty,
                "wechat_version": info?["CFBundleShortVersionString"] ?? "unknown",
                "wechat_build": info?["CFBundleVersion"] ?? "unknown"]
    }
    let app = try application()
    if action == "snapshot" { return try snapshot(app, directory: args["directory"] as? String ?? NSTemporaryDirectory()) }
    if action == "observe" { return try snapshot(app, directory: args["directory"] as? String ?? NSTemporaryDirectory(), activateWindow: false) }
    let rect = try verifyWindow(args, app)
    switch action {
    case "click":
        guard let x = args["x"] as? Double, let y = args["y"] as? Double,
              x >= 0, y >= 0, x < rect["Width"]!, y < rect["Height"]! else { try fail("Invalid click coordinates.") }
        click(CGPoint(x: rect["X"]! + x, y: rect["Y"]! + y), right: args["right"] as? Bool ?? false)
    case "key":
        let name = args["key"] as? String ?? ""
        switch name {
        case "search": press(3, flags: .maskCommand)
        case "escape": press(53)
        case "return": press(36)
        case "select_all": press(0, flags: .maskCommand)
        case "backspace": press(51)
        default: try fail("Unsupported key.")
        }
    case "paste":
        guard let text = args["text"] as? String else { try fail("Missing text.") }
        withClipboard { board in
            board.clearContents(); board.setString(text, forType: .string)
            if args["replace"] as? Bool == true { press(0, flags: .maskCommand); usleep(80_000) }
            press(9, flags: .maskCommand); usleep(250_000)
        }
    case "copy_input":
        return withClipboard { board in
            board.clearContents(); press(0, flags: .maskCommand); usleep(80_000)
            press(8, flags: .maskCommand); usleep(200_000)
            return ["text": board.string(forType: .string) ?? ""]
        }
    default: try fail("Unsupported action.")
    }
    usleep(180_000)
    return ["ok": true]
}
do {
    let data = FileHandle.standardInput.readDataToEndOfFile()
    let args = try JSONSerialization.jsonObject(with: data) as? [String:Any] ?? [:]
    let result = try run(args)
    let output = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
    print(String(data: output, encoding: .utf8)!)
} catch {
    let result = ["error": error.localizedDescription]
    let output = try! JSONSerialization.data(withJSONObject: result)
    print(String(data: output, encoding: .utf8)!)
    exit(1)
}
