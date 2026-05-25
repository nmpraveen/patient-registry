package com.naveenhospital.medtrack.core.data.auth

import android.content.Context
import android.content.SharedPreferences
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertFalse
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
        val lockStore = LockStore(prefs)

        lockStore.savePattern(listOf(0, 1, 4, 8))

        assertTrue(lockStore.hasPattern())
        assertTrue(lockStore.hasAnyLock())
        assertTrue(lockStore.verifyPattern(listOf(0, 1, 4, 8)))
        assertFalse(lockStore.verifyPattern(listOf(0, 1, 5, 8)))

        val restoredStore = LockStore(prefs)
        assertTrue(restoredStore.hasPattern())
        assertTrue(restoredStore.verifyPattern(listOf(0, 1, 4, 8)))
    }

    @Test
    fun patternRequiresAtLeastFourDots() {
        val lockStore = LockStore(prefs)

        assertThrows(IllegalArgumentException::class.java) {
            lockStore.savePattern(listOf(0, 1, 2))
        }

        assertFalse(lockStore.hasPattern())
        assertFalse(lockStore.verifyPattern(listOf(0, 1, 2)))
    }

    @Test
    fun biometricFlagContributesToAnyLockState() {
        val lockStore = LockStore(prefs)

        assertFalse(lockStore.isBiometricEnabled())
        assertFalse(lockStore.hasAnyLock())

        lockStore.setBiometricEnabled(true)

        assertTrue(lockStore.isBiometricEnabled())
        assertTrue(lockStore.hasAnyLock())

        val restoredStore = LockStore(prefs)
        assertTrue(restoredStore.isBiometricEnabled())
        assertTrue(restoredStore.hasAnyLock())
    }

    @Test
    fun clearRemovesPatternAndBiometricState() {
        val lockStore = LockStore(prefs)
        lockStore.savePattern(listOf(0, 1, 4, 8))
        lockStore.setBiometricEnabled(true)

        lockStore.clear()

        val restoredStore = LockStore(prefs)
        assertFalse(restoredStore.hasPattern())
        assertFalse(restoredStore.isBiometricEnabled())
        assertFalse(restoredStore.hasAnyLock())
    }
}
