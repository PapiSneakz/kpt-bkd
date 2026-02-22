from app.kluspilot.tenant_auth import hash_password

new_pass = "NieuwSterkWachtwoord123!"
print(hash_password(new_pass))
