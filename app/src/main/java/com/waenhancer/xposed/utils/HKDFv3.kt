package com.waenhancer.xposed.utils

import java.io.ByteArrayOutputStream
import java.security.InvalidKeyException
import java.security.NoSuchAlgorithmException
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import kotlin.math.ceil

/**
 * HKDF (HMAC-based Extract-and-Expand Key Derivation Function) implementation matching WhatsApp's standard.
 */
class HKDFv3 {

    fun deriveSecrets(inputKeyMaterial: ByteArray, salt: ByteArray = ByteArray(32), info: ByteArray?, outputLength: Int): ByteArray {
        val prk: ByteArray
        try {
            val mac = Mac.getInstance("HmacSHA256")
            mac.init(SecretKeySpec(salt, "HmacSHA256"))
            prk = mac.doFinal(inputKeyMaterial)
        } catch (e: Exception) {
            throw AssertionError(e)
        }

        try {
            val iterations = ceil(outputLength.toDouble() / 32.0).toInt()
            var outputKey = ByteArray(0)
            val outputStream = ByteArrayOutputStream()
            var remainingLength = outputLength

            for (i in 1 until 1 + iterations) {
                val macIteration = Mac.getInstance("HmacSHA256")
                macIteration.init(SecretKeySpec(prk, "HmacSHA256"))
                macIteration.update(outputKey)
                if (info != null) {
                    macIteration.update(info)
                }
                macIteration.update(i.toByte())
                outputKey = macIteration.doFinal()
                val count = minOf(remainingLength, outputKey.size)
                outputStream.write(outputKey, 0, count)
                remainingLength -= count
            }
            return outputStream.toByteArray()
        } catch (ex: Exception) {
            throw AssertionError(ex)
        }
    }
}
