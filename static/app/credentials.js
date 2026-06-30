async function storeLoginCredential(username, password) {
  if (!username || !password || !window.PasswordCredential || !navigator.credentials) return;
  try {
    await navigator.credentials.store(new PasswordCredential({ id: username, name: username, password }));
  } catch (error) {
    // Browser password managers and autocomplete remain the fallback.
  }
}

async function prefillLoginCredential() {
  if (!window.PasswordCredential || !navigator.credentials) return;
  try {
    const credential = await navigator.credentials.get({ password: true, mediation: "optional" });
    if (!credential || !credential.id || !credential.password) return;
    const usernameInput = document.querySelector("#loginForm input[name='username']");
    const passwordInput = document.querySelector("#loginForm input[name='password']");
    if (usernameInput) usernameInput.value = credential.id;
    if (passwordInput) passwordInput.value = credential.password;
  } catch (error) {
    // Ignore unsupported or denied credential access.
  }
}

export { storeLoginCredential, prefillLoginCredential };
