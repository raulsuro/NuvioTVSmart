#!/usr/bin/env python3
"""Apply strict, reviewable LG webOS login recovery edits to NuvioTVSmart 1.3.7.

Run from the upstream checkout root, *after* the four pre-existing custom patches.
Each anchor must match once so upstream changes cause a safe CI failure.
"""
from pathlib import Path


def replace_once(path: str, original: str, updated: str) -> None:
    file = Path(path)
    source = file.read_text(encoding="utf-8")
    count = source.count(original)
    if count != 1:
        raise RuntimeError(f"{path}: expected one edit anchor; found {count}. Upstream changed; aborting.")
    file.write_text(source.replace(original, updated, 1), encoding="utf-8")
    print(f"Updated {path}")


qr_file = "js/ui/screens/account/authQrSignInScreenMethods-02-bind-controls.js"
back_file = "js/ui/screens/account/authQrSignInScreenMethods-03-to-friendly-email-error.js"

# 1. Make missing QR sessions actionable on the TV instead of showing a white box.
replace_once(qr_file, '''        if (!result || !result.code) {
          this.setStatus(this.toFriendlyQrError(QrLoginService.getLastError()));
          return;
        }
        this.renderQr(result);
        this.setStatus(I18n.t("auth.qr.scanAndSignIn"));
        this.startPolling(result.code, result.deviceNonce, result.pollIntervalSeconds || 3);
      } finally {
''', '''        if (!result || !result.code) {
          this.setQrUnavailable(this.toFriendlyQrError(QrLoginService.getLastError()));
          return;
        }
        this.renderQr(result);
        this.setStatus(I18n.t("auth.qr.scanAndSignIn"));
        this.startPolling(result.code, result.deviceNonce, result.pollIntervalSeconds || 3);
      } catch (error) {
        console.warn("QR login start failed", error);
        if (this.isMounted && !this.isLeaving) {
          this.setQrUnavailable(this.toFriendlyQrError(error?.message || error));
        }
      } finally {
''')

# A valid login session still has a manual verification URI and code even if
# the TV's canvas/QR library fails. Make them visible as a usable fallback.
replace_once(qr_file, '''      const content = String(loginUrl || "").trim();
      if (!content) {
        qrContainer.innerHTML = `<span class="qr-code-unavailable">${escapeHtml(I18n.t("auth.qr.unavailable"))}</span>`;
      } else {
        qrContainer.innerHTML = `<canvas class="qr-image qr-image-canvas" aria-label="${escapeHtml(
          I18n.t("auth.qr.qrImageAlt")
        )}"></canvas>`;
        try {
          QrCodeGenerator.generate(qrContainer.querySelector("canvas"), content, 320);
        } catch (error) {
          console.warn("Unable to render QR code locally", error);
          qrContainer.innerHTML = `<span class="qr-code-unavailable">${escapeHtml(I18n.t("auth.qr.unavailable"))}</span>`;
        }
      }
''', '''      const content = String(loginUrl || "").trim();
      const showManualFallback = () => {
        const url = String(verificationUri || "").replace(/^https?:\\/\\//i, "").replace(/\\/+$/, "");
        const instructions = url
          ? `QR cannot be displayed. Open ${url} on your phone and enter the code below.`
          : "QR cannot be displayed. Use the manual verification code below.";
        qrContainer.innerHTML = `<span class="qr-code-unavailable">${escapeHtml(instructions)}</span>`;
      };
      if (!content) {
        showManualFallback();
      } else {
        qrContainer.innerHTML = `<canvas class="qr-image qr-image-canvas" aria-label="${escapeHtml(
          I18n.t("auth.qr.qrImageAlt")
        )}"></canvas>`;
        try {
          const canvas = qrContainer.querySelector("canvas");
          QrCodeGenerator.generate(canvas, content, 320);
          // Some older webOS runtimes leave a white canvas without throwing.
          // Detect a blank QR and show a manual activation path instead.
          const context = canvas?.getContext?.("2d");
          if (!context?.getImageData) throw new Error("QR canvas unavailable");
          const pixels = context.getImageData(0, 0, 320, 320).data;
          let darkPixels = 0;
          for (let i = 0; i < pixels.length; i += 16) {
            if (pixels[i] < 80 && pixels[i + 1] < 80 && pixels[i + 2] < 80) {
              if (++darkPixels > 64) break;
            }
          }
          if (darkPixels <= 64) throw new Error("QR canvas is blank");
        } catch (error) {
          console.warn("Unable to render QR code locally", error);
          showManualFallback();
        }
      }
''')

replace_once(qr_file, '''    startCountdown(expiresAt) {
''', '''    setQrUnavailable(message) {
      this.clearQr();
      const text = String(message || "QR login is unavailable. Check the app configuration.");
      const panel = this.container?.querySelector("#qr-container");
      if (panel) {
        panel.innerHTML = `<span class="qr-code-unavailable">${escapeHtml(text)}</span>`;
      }
      this.setStatus(text);
    },
    startCountdown(expiresAt) {
''')

# 2. A signed-out return route may be empty following sign-out. Back should
# never dispatch a route to a blank screen or silently enable guest access.
replace_once(back_file, '''      this.cleanup();
      if (!this.onboardingMode && this.hasBackDestination) {
        Router.back();
        return;
      }
      Router.navigate("home", {}, { replaceHistory: true, skipStackPush: true });
''', '''      this.cleanup();
      // After sign-out, the previous authenticated screen is not a safe route.
      // Explicit onboarding guest continuation retains the original behavior.
      if (!this.isSignedIn && !this.onboardingMode) {
        Platform.exitApp();
        return;
      }
      if (!this.onboardingMode && this.hasBackDestination) {
        Router.back();
        return;
      }
      Router.navigate("home", {}, { replaceHistory: true, skipStackPush: true });
''')
replace_once(back_file, '''      if (this.onboardingMode) {
        // Android finishes the onboarding activity on hardware Back. Do not
        // silently turn Back into the explicit guest opt-in action.
        Platform.exitApp();
        return;
      }
      Router.back({ skipConsume: true });
''', '''      if (this.onboardingMode || !this.isSignedIn) {
        // Signed-out Back should exit instead of restoring an unusable route.
        // Never turn Back into an implicit guest opt-in.
        Platform.exitApp();
        return;
      }
      Router.back({ skipConsume: true });
''')
print("Login recovery edits applied. Run tests and package verification in CI.")
