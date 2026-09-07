package com.naveenhospital.medtrack.core.data.auth

import android.content.Context

/** Synthetic preferences for session tests; device Keystore acceptance is a separate gate. */
fun testTokenStore(context: Context): TokenStore =
    TokenStore(context.getSharedPreferences("test_push_auth", Context.MODE_PRIVATE))

fun testLockStore(context: Context): LockStore =
    LockStore(context.getSharedPreferences("test_push_lock", Context.MODE_PRIVATE))
