(() => {
    const config = document.getElementById("device-verification-script").dataset;
    const csrfToken = config.csrfToken;
    const statusEl = document.getElementById("device-status");
    const verifyButton = document.getElementById("verify-device-button");
    const registerButton = document.getElementById("register-device-button");
    const deviceLabelInput = document.getElementById("device-label");

    const setStatus = (message, level = "secondary") => {
      statusEl.className = `alert alert-${level}`;
      statusEl.textContent = message;
    };

    const isWebAuthnAvailable = Boolean(window.PublicKeyCredential && navigator.credentials);

    if (!isWebAuthnAvailable) {
      setStatus("This browser does not support passkeys / WebAuthn.", "danger");
      if (verifyButton) verifyButton.disabled = true;
      if (registerButton) registerButton.disabled = true;
      return;
    }

    const decodeBase64url = (value) => {
      const padding = "=".repeat((4 - (value.length % 4)) % 4);
      const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
      const binary = atob(base64);
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index);
      }
      return bytes.buffer;
    };

    const encodeBase64url = (value) => {
      const bytes = value instanceof ArrayBuffer ? new Uint8Array(value) : new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
      let binary = "";
      bytes.forEach((byte) => {
        binary += String.fromCharCode(byte);
      });
      return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
    };

    const credentialToJSON = (credential) => {
      const response = {};
      for (const name of ["clientDataJSON", "attestationObject", "authenticatorData", "signature", "userHandle"]) {
        const value = credential.response[name];
        if (value !== undefined) response[name] = value === null ? null : encodeBase64url(value);
      }
      return {
        id: credential.id,
        rawId: encodeBase64url(credential.rawId),
        type: credential.type,
        response,
        clientExtensionResults: credential.getClientExtensionResults?.() || {},
        authenticatorAttachment: credential.authenticatorAttachment || null,
      };
    };

    const creationOptionsFromJSON = (options) => {
      if (window.PublicKeyCredential.parseCreationOptionsFromJSON) {
        return window.PublicKeyCredential.parseCreationOptionsFromJSON(options);
      }
      const publicKey = JSON.parse(JSON.stringify(options));
      publicKey.challenge = decodeBase64url(publicKey.challenge);
      publicKey.user.id = decodeBase64url(publicKey.user.id);
      if (publicKey.excludeCredentials) {
        publicKey.excludeCredentials = publicKey.excludeCredentials.map((credential) => ({
          ...credential,
          id: decodeBase64url(credential.id),
        }));
      }
      return publicKey;
    };

    const requestOptionsFromJSON = (options) => {
      if (window.PublicKeyCredential.parseRequestOptionsFromJSON) {
        return window.PublicKeyCredential.parseRequestOptionsFromJSON(options);
      }
      const publicKey = JSON.parse(JSON.stringify(options));
      publicKey.challenge = decodeBase64url(publicKey.challenge);
      if (publicKey.allowCredentials) {
        publicKey.allowCredentials = publicKey.allowCredentials.map((credential) => ({
          ...credential,
          id: decodeBase64url(credential.id),
        }));
      }
      return publicKey;
    };

    const postJson = async (url, payload = {}) => {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.message || "Request failed.");
      }
      return data;
    };

    const describeWebAuthnError = (error, fallbackMessage) => {
      const message = error?.message || "";
      if (error?.name === "NotAllowedError") {
        return "The passkey prompt was cancelled or blocked by the device/browser. If iPhone asks to save the passkey, allow it to continue.";
      }
      if (error?.name === "InvalidStateError") {
        return "This device already has a passkey for this account. Ask an admin to approve it, or use Verify Approved Device after approval.";
      }
      if (error?.name === "SecurityError") {
        return "This browser blocked passkey registration in the current security context. Reload the page and try again from the HTTPS tunnel link.";
      }
      return message || fallbackMessage;
    };

    const toggleButtons = (disabled) => {
      if (verifyButton) verifyButton.disabled = disabled || verifyButton.dataset.locked === "true";
      if (registerButton) registerButton.disabled = disabled || registerButton.dataset.locked === "true";
    };

    if (verifyButton && verifyButton.disabled) {
      verifyButton.dataset.locked = "true";
    }
    if (registerButton && registerButton.disabled) {
      registerButton.dataset.locked = "true";
    }

    if (registerButton) {
      registerButton.addEventListener("click", async () => {
        const deviceLabel = (deviceLabelInput.value || "").trim();
        if (!deviceLabel) {
          setStatus("Enter a device label before registering this browser.", "warning");
          deviceLabelInput.focus();
          return;
        }

        toggleButtons(true);
        setStatus("Requesting registration options...", "secondary");

        try {
          const options = await postJson(config.registerOptionsUrl);
          const credential = await navigator.credentials.create({
            publicKey: creationOptionsFromJSON(options),
          });
          const credentialJson = credential.toJSON ? credential.toJSON() : credentialToJSON(credential);
          credentialJson.authenticatorAttachment = credential.authenticatorAttachment || "";
          if (credential.response && credential.response.getTransports) {
            credentialJson.transports = credential.response.getTransports();
          }
          const result = await postJson(config.registerVerifyUrl, {
            device_label: deviceLabel,
            credential: credentialJson,
          });
          setStatus(result.message || "Device registered. Await admin approval.", "info");
        } catch (error) {
          setStatus(describeWebAuthnError(error, "Device registration failed."), "danger");
        } finally {
          toggleButtons(false);
        }
      });
    }

    if (verifyButton) {
      verifyButton.addEventListener("click", async () => {
        toggleButtons(true);
        setStatus("Requesting verification options...", "secondary");

        try {
          const options = await postJson(config.authenticateOptionsUrl);
          const assertion = await navigator.credentials.get({
            publicKey: requestOptionsFromJSON(options),
          });
          const assertionJson = assertion.toJSON ? assertion.toJSON() : credentialToJSON(assertion);
          const result = await postJson(config.authenticateVerifyUrl, {
            credential: assertionJson,
          });
          setStatus(result.message || "Device verified. Redirecting...", "success");
          window.location.assign(result.redirect_url || config.dashboardUrl);
        } catch (error) {
          setStatus(describeWebAuthnError(error, "Device verification failed."), "danger");
          toggleButtons(false);
        }
      });
    }
  })();
