use apcos_os::secure_storage::SecureStorage;

#[test]
fn secure_storage_compat_passthrough_round_trip() {
    let storage = SecureStorage::with_generated_key();
    let plaintext = b"apcos-stage15-payload";
    let aad = b"stage15";

    let encrypted = storage.encrypt(plaintext, aad);
    assert!(encrypted.is_ok());

    let encrypted_bytes = encrypted.unwrap_or_default();
    let decrypted = storage.decrypt(&encrypted_bytes, aad);
    assert!(decrypted.is_ok());
    assert_eq!(decrypted.unwrap_or_default(), plaintext);
}

#[test]
fn secure_storage_contains_no_filesystem_operations() {
    let source = include_str!("../src/secure_storage.rs");
    assert!(!source.contains("std::fs"));
    assert!(!source.contains("fs::write("));
    assert!(!source.contains("fs::read("));
}
