package com.naveenhospital.medtrack.core.data.auth

import android.content.Context
import android.content.SharedPreferences
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.assertThrows
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class TokenStoreTest {
    private lateinit var context: Context
    private lateinit var prefs: SharedPreferences

    @Before
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        prefs = context.getSharedPreferences("test_medtrack_auth", Context.MODE_PRIVATE)
        prefs.edit().clear().commit()
    }

    @After
    fun tearDown() {
        prefs.edit().clear().commit()
    }

    @Test
    fun refreshTokenPersistsButAccessTokenStaysInMemoryOnly() {
        val tokenStore = TokenStore(prefs)

        assertTrue(tokenStore.commitVerifiedSession(ACCOUNT_ID, access = "access-token", refresh = "refresh-token"))

        assertEquals("access-token", tokenStore.accessToken)
        assertEquals("refresh-token", tokenStore.refreshToken())
        assertEquals(ACCOUNT_ID, tokenStore.accountId())
        assertTrue(tokenStore.hasRefreshToken())

        val restoredStore = TokenStore(prefs)
        assertNull(restoredStore.accessToken)
        assertEquals("refresh-token", restoredStore.refreshToken())
        assertTrue(restoredStore.hasRefreshToken())
    }

    @Test
    fun saveSessionWithoutRefreshKeepsExistingRefreshToken() {
        val tokenStore = TokenStore(prefs)

        assertTrue(tokenStore.commitVerifiedSession(ACCOUNT_ID, access = "access-token-1", refresh = "refresh-token"))
        assertTrue(tokenStore.updateSessionForAccount(ACCOUNT_ID, access = "access-token-2", refresh = null))

        assertEquals("access-token-2", tokenStore.accessToken)
        assertEquals("refresh-token", tokenStore.refreshToken())
    }

    @Test
    fun clearRemovesRefreshAndAccessTokens() {
        val tokenStore = TokenStore(prefs)
        assertTrue(tokenStore.commitVerifiedSession(ACCOUNT_ID, access = "access-token", refresh = "refresh-token"))

        tokenStore.clear()

        assertNull(tokenStore.accessToken)
        assertNull(TokenStore(prefs).refreshToken())
        assertFalse(tokenStore.hasRefreshToken())
    }

    @Test
    fun accountBoundTokenAccessRejectsAnotherAccount() {
        val tokenStore = TokenStore(prefs)
        assertTrue(tokenStore.commitVerifiedSession(ACCOUNT_ID, "access-token", "refresh-token"))

        assertNull(tokenStore.accessTokenFor("2"))
        assertNull(tokenStore.refreshTokenFor("2"))
        assertFalse(tokenStore.updateSessionForAccount("2", "attacker-access", "attacker-refresh"))
        assertEquals("access-token", tokenStore.accessTokenFor(ACCOUNT_ID))
    }

    @Test
    fun failedPreferenceCommitsNeverExposeCandidateTokensAndClearFailsClosed() {
        val failingStore = TokenStore(failingCommitPreferences(prefs))

        assertFalse(failingStore.commitVerifiedSession(ACCOUNT_ID, "candidate", "refresh"))
        assertNull(failingStore.accessToken)
        assertNull(failingStore.accountId())

        val goodStore = TokenStore(prefs)
        assertTrue(goodStore.commitVerifiedSession(ACCOUNT_ID, "access", "refresh"))
        val failingClearStore = TokenStore(failingCommitPreferences(prefs))
        assertThrows(IllegalStateException::class.java) { failingClearStore.clear() }
        assertNull(failingClearStore.accessToken)
    }

    private companion object {
        const val ACCOUNT_ID = "1"
    }
}
