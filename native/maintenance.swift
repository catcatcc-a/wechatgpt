import AppKit
import ApplicationServices
import Foundation
let apps = NSRunningApplication.runningApplications(withBundleIdentifier: "com.tencent.xinWeChat")
let mode = CommandLine.arguments.dropFirst().first ?? "status"
if mode == "quit" {
    for app in apps { if !app.terminate() { fputs("Graceful quit rejected\n", stderr); exit(2) } }
    for _ in 0..<100 {
        RunLoop.current.run(until: Date().addingTimeInterval(0.1))
        if NSRunningApplication.runningApplications(withBundleIdentifier: "com.tencent.xinWeChat").isEmpty { print("quit"); exit(0) }
    }
    fputs("WeChat did not quit; inspect a possible confirmation dialog.\n", stderr); exit(2)
} else if mode == "resize" {
    guard AXIsProcessTrusted(), let app = apps.first else { exit(2) }
    let element = AXUIElementCreateApplication(app.processIdentifier)
    var value: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, kAXWindowsAttribute as CFString, &value) == .success,
          let windows = value as? [AXUIElement], let window = windows.first else { exit(2) }
    let frame = NSScreen.main?.frame ?? CGRect(x:0,y:0,width:1470,height:956)
    var size = CGSize(width: min(880, frame.width-60), height: min(640,frame.height-100))
    var point = CGPoint(x: max(20,frame.width-size.width-20), y: 65)
    let sizeValue = AXValueCreate(.cgSize, &size)!
    let posValue = AXValueCreate(.cgPoint, &point)!
    let s = AXUIElementSetAttributeValue(window, kAXSizeAttribute as CFString, sizeValue)
    let p = AXUIElementSetAttributeValue(window, kAXPositionAttribute as CFString, posValue)
    print("resize",s.rawValue,p.rawValue)
} else { print("running",apps.map{$0.processIdentifier}) }
