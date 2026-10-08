# CYBERGUARD Chrome Extension

The extension reuses the existing Python detection service. The browser package observes HTTP/HTTPS page loads only when monitoring is enabled; it submits the URL and a bounded summary of login-form structure to `127.0.0.1`. It does not read form values or page text. URL/form signals flow through the existing analyzer and qualifying results are recorded in the normal local incident store.

## Install

1. Set up the repository and local Python service using the [main README](../README.md). The service listens on loopback at `127.0.0.1:8765`.
2. Build the unpacked extension from the repository root:

   ```powershell
   python extension\build_extension.py
   ```

3. Open `chrome://extensions`, enable **Developer mode**, select **Load unpacked**, and choose `extension\build`.
4. Open the extension popup and turn **Website monitoring** on. Chrome will ask for access to websites; declining leaves monitoring off.
5. To start the Python service automatically at Windows sign-in, run this once from PowerShell:

   ```powershell
   .\extension\Install-Startup.ps1
   ```

   Remove the scheduled task at any time with `.\extension\Uninstall-Startup.ps1`.

## Runtime and controls

- The monitoring toggle is off by default and its choice is saved across Chrome restarts. When enabled, a registered Manifest V3 content script resumes on HTTP/HTTPS pages as Chrome opens them; the service worker is event-driven and Chrome may suspend it between events.
- Chrome must be running and Windows must be awake and signed in. This is not a kernel-level or pre-login service and cannot inspect pages while Chrome is closed, a device is asleep, or a page is on a restricted Chrome URL.
- Use the extension popup toggle to stop monitoring and revoke its website permission. Uninstalling the extension also stops browser monitoring. The Python API can be stopped separately from Task Scheduler or its process manager.
- The extension does not block navigation. It displays elevated-risk status on its toolbar icon and adds qualifying findings to the existing incident queue. Review the analysis before taking action.
- Automatic URL analyses count as live analyses and can create local incidents when risk reaches the configured threshold (50). Normal pages also contribute to local analysis totals.
- Browser history URLs, including query strings, are sent only to the loopback service and may appear in qualifying incident summaries. Do not use monitoring on profiles or websites where local URL processing is not appropriate.

The extension asks for broad website access only after the user turns monitoring on. It sends page URLs, titles and a capped login-form structure summary; it does not collect field values or page body text. Monitoring can resume after a Chrome restart only if it was enabled and the permission remains granted.