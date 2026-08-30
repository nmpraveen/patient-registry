package com.naveenhospital.medtrack.core.data.auth

import android.content.Context
import android.content.SharedPreferences
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class MobileDeviceCredentialStoreTest {
    private lateinit var prefs: SharedPreferences

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        prefs = context.getSharedPreferences("test_mobile_device_credentials", Context.MODE_PRIVATE)
        prefs.edit().clear().commit()
    }

    @After
    fun tearDown() {
        prefs.edit().clear().commit()
    }

    @Test
    fun credentialsAreUsernameBoundAndClearedIndependently() {
        val store = MobileDeviceCredentialStore(prefs, "Ward Android")
        val first = MobileDeviceCredential(FIRST_DEVICE_ID, "first-secret")
        val second = MobileDeviceCredential(SECOND_DEVICE_ID, "second-secret")

        assertTrue(store.save("Doctor.One", first))
        assertTrue(store.save("doctor.two", second))

        assertEquals(first, store.credentialFor(" doctor.one "))
        assertEquals(second, store.credentialFor("DOCTOR.TWO"))
        assertTrue(store.clear("doctor.one"))
        assertNull(store.credentialFor("doctor.one"))
        assertEquals(second, store.credentialFor("doctor.two"))
    }

    @Test
    fun malformedCredentialsAndFailedEncryptedPreferenceCommitsFailClosed() {
        val store = MobileDeviceCredentialStore(prefs, "Ward Android")
        assertFalse(store.save("doctor", MobileDeviceCredential("not-a-uuid", "secret")))
        assertFalse(store.save("doctor", MobileDeviceCredential(FIRST_DEVICE_ID, "")))
        assertNull(store.credentialFor("doctor"))

        val failingStore = MobileDeviceCredentialStore(
            failingCommitPreferences(prefs),
            "Ward Android",
        )
        assertFalse(
            failingStore.save(
                "doctor",
                MobileDeviceCredential(FIRST_DEVICE_ID, "one-time-secret"),
            ),
        )
        assertNull(store.credentialFor("doctor"))
        assertFalse(failingStore.clear("doctor"))
    }

    private companion object {
        const val FIRST_DEVICE_ID = "11111111-1111-4111-8111-111111111111"
        const val SECOND_DEVICE_ID = "22222222-2222-4222-8222-222222222222"
    }
}
