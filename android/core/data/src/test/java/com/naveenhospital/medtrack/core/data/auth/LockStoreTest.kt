package com.naveenhospital.medtrack.core.data.auth

import android.content.Context
import android.content.SharedPreferences
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class LockStoreTest {
    private lateinit var context: Context
    private lateinit var prefs: SharedPreferences

    @Before
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        prefs = context.getSharedPreferences("test_medtrack_lock", Context.MODE_PRIVATE)
        prefs.edit().clear().commit()
    }

    @After
    fun tearDown() {
        prefs.edit().clear().commit()
    }

    @Test
    fun patternIsSaltedPersistedAndVerified() {
        val lockStore = LockStore(prefs).also { it.activateAccount(ACCOUNT_ID) }

        lockStore.savePattern(listOf(0, 1, 4, 8))

        assertTrue(lockStore.hasPattern())
        assertTrue(lockStore.hasAnyLock())
        assertEquals(LockVerificationResult.Success, lockStore.verifyPattern(listOf(0, 1, 4, 8)))
        assertEquals(LockVerificationResult.Invalid, lockStore.verifyPattern(listOf(0, 1, 5, 8)))

        val restoredStore = LockStore(prefs).also { it.activateAccount(ACCOUNT_ID) }
        assertTrue(restoredStore.hasPattern())
        assertEquals(LockVerificationResult.Success, restoredStore.verifyPattern(listOf(0, 1, 4, 8)))
    }

    @Test
    fun patternRequiresAtLeastFourDots() {
        val lockStore = LockStore(prefs).also { it.activateAccount(ACCOUNT_ID) }

        assertThrows(IllegalArgumentException::class.java) {
            lockStore.savePattern(listOf(0, 1, 2))
        }

        assertFalse(lockStore.hasPattern())
        assertEquals(LockVerificationResult.ReauthenticationRequired, lockStore.verifyPattern(listOf(0, 1, 2)))
    }

    @Test
    fun biometricFlagContributesToAnyLockState() {
        val lockStore = LockStore(prefs).also { it.activateAccount(ACCOUNT_ID) }

        assertFalse(lockStore.isBiometricEnabled())
        assertFalse(lockStore.hasAnyLock())

        lockStore.setBiometricEnabled(true)

        assertTrue(lockStore.isBiometricEnabled())
        assertTrue(lockStore.hasAnyLock())

        val restoredStore = LockStore(prefs).also { it.activateAccount(ACCOUNT_ID) }
        assertTrue(restoredStore.isBiometricEnabled())
        assertTrue(restoredStore.hasAnyLock())
    }

    @Test
    fun clearRemovesPatternAndBiometricState() {
        val lockStore = LockStore(prefs).also { it.activateAccount(ACCOUNT_ID) }
        lockStore.savePattern(listOf(0, 1, 4, 8))
        lockStore.setBiometricEnabled(true)

        lockStore.clearActiveAccount()

        val restoredStore = LockStore(prefs).also { it.activateAccount(ACCOUNT_ID) }
        assertFalse(restoredStore.hasPattern())
        assertFalse(restoredStore.isBiometricEnabled())
        assertFalse(restoredStore.hasAnyLock())
    }

    @Test
    fun lockNeverTransfersToAnotherAccount() {
        val lockStore = LockStore(prefs).also { it.activateAccount(ACCOUNT_ID) }
        lockStore.savePattern(listOf(0, 1, 4, 8))

        lockStore.activateAccount("2")

        assertFalse(lockStore.hasAnyLock())
        assertEquals(LockVerificationResult.ReauthenticationRequired, lockStore.verifyPattern(listOf(0, 1, 4, 8)))
    }

    @Test
    fun repeatedFailuresAreThrottledAndEventuallyRequirePassword() {
        var now = 10_000L
        val lockStore = LockStore(prefs, nowMillis = { now }).also { it.activateAccount(ACCOUNT_ID) }
        lockStore.savePattern(listOf(0, 1, 4, 8))

        repeat(4) {
            assertEquals(LockVerificationResult.Invalid, lockStore.verifyPattern(listOf(0, 1, 5, 8)))
        }
        val throttled = lockStore.verifyPattern(listOf(0, 1, 5, 8))
        assertTrue(throttled is LockVerificationResult.Throttled)
        repeat(5) {
            now += 10 * 60_000L
            lockStore.verifyPattern(listOf(0, 1, 5, 8))
        }

        assertFalse(lockStore.hasAnyLock())
    }

    @Test
    fun failedPreferenceCommitCannotUnlockOrCreateLockState() {
        prefs.edit().putBoolean("owner_lock_migration_complete", true).commit()
        val failingStore = LockStore(failingCommitPreferences(prefs)).also { it.activateAccount(ACCOUNT_ID) }
        assertThrows(IllegalStateException::class.java) {
            failingStore.savePattern(listOf(0, 1, 4, 8))
        }
        assertFalse(failingStore.hasPattern())
        assertEquals(null, failingStore.activeAccountId())

        val goodStore = LockStore(prefs).also { it.activateAccount(ACCOUNT_ID) }
        goodStore.savePattern(listOf(0, 1, 4, 8))
        val failingVerificationStore = LockStore(failingCommitPreferences(prefs)).also {
            it.activateAccount(ACCOUNT_ID)
        }
        assertEquals(
            LockVerificationResult.ReauthenticationRequired,
            failingVerificationStore.verifyPattern(listOf(0, 1, 4, 8)),
        )
        assertEquals(null, failingVerificationStore.activeAccountId())
    }

    private companion object {
        const val ACCOUNT_ID = "1"
    }
}
