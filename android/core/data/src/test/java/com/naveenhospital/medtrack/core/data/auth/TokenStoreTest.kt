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

        tokenStore.saveSession(access = "access-token", refresh = "refresh-token")

        assertEquals("access-token", tokenStore.accessToken)
        assertEquals("refresh-token", tokenStore.refreshToken())
        assertTrue(tokenStore.hasRefreshToken())

        val restoredStore = TokenStore(prefs)
        assertNull(restoredStore.accessToken)
        assertEquals("refresh-token", restoredStore.refreshToken())
        assertTrue(restoredStore.hasRefreshToken())
    }

    @Test
    fun saveSessionWithoutRefreshKeepsExistingRefreshToken() {
        val tokenStore = TokenStore(prefs)

        tokenStore.saveSession(access = "access-token-1", refresh = "refresh-token")
        tokenStore.saveSession(access = "access-token-2", refresh = null)

        assertEquals("access-token-2", tokenStore.accessToken)
        assertEquals("refresh-token", tokenStore.refreshToken())
    }

    @Test
    fun clearRemovesRefreshAndAccessTokens() {
        val tokenStore = TokenStore(prefs)
        tokenStore.saveSession(access = "access-token", refresh = "refresh-token")

        tokenStore.clear()

        assertNull(tokenStore.accessToken)
        assertNull(TokenStore(prefs).refreshToken())
        assertFalse(tokenStore.hasRefreshToken())
    }
}
