import JSEncrypt from 'jsencrypt'

export function encrypt(data, publicKey) {
  const encryptor = new JSEncrypt()
  encryptor.setPublicKey(publicKey)
  return encryptor.encrypt(data)
}

export function decrypt(data, privateKey) {
  const encryptor = new JSEncrypt()
  encryptor.setPrivateKey(privateKey)
  return encryptor.decrypt(data)
}

export function encryptPassword(password, publicKey) {
  return encrypt(password, publicKey)
}

export function decryptPassword(encrypted, privateKey) {
  return decrypt(encrypted, privateKey)
}
