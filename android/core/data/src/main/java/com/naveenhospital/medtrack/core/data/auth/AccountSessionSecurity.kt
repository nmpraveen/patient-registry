package com.naveenhospital.medtrack.core.data.auth

import android.content.Context
import com.naveenhospital.medtrack.core.data.local.MedtrackDatabase
import com.naveenhospital.medtrack.core.data.sync.MedtrackSyncWorker
import com.squareup.moshi.JsonDataException
import java.io.IOException
import java.util.concurrent.CopyOnWriteArraySet
import retrofit2.HttpException
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext

sealed interface SessionRestoreResult {
    data class Verified(val profile: com.naveenhospital.medtrack.core.network.model.UserProfileDto) : SessionRestoreResult
    data class Retryable(val cause: Throwable) : SessionRestoreResult
    data object NoSession : SessionRestoreResult
}

internal class DefinitiveAccountIdentityException(
    message: String,
    cause: Throwable? = null,
) : IllegalStateException(message, cause)

fun Throwable.isDefinitiveAccountAuthFailure(): Boolean =
    when (this) {
        is DefinitiveAccountIdentityException -> true
        is JsonDataException -> true
        is HttpException -> code() in setOf(400, 401, 403)
        is IOException -> false
        else -> false
    }

sealed interface AccountSessionRefreshResult {
    data object Verified : AccountSessionRefreshResult
    data object StaleAccount : AccountSessionRefreshResult
    data class Retryable(val cause: Throwable) : AccountSessionRefreshResult
    data class DefinitiveFailure(val cause: Throwable) : AccountSessionRefreshResult
}

suspend fun refreshAndVerifyAccountSession(
    ownerAccountId: String,
    tokenStore: TokenStore,
    refreshSession: suspend (String) -> com.naveenhospital.medtrack.core.network.model.AuthSessionDto,
    verifyProfile: suspend (String) -> com.naveenhospital.medtrack.core.network.model.UserProfileDto,
): AccountSessionRefreshResult {
    if (tokenStore.accountId() != ownerAccountId) return AccountSessionRefreshResult.StaleAccount
    val refreshToken = tokenStore.refreshTokenFor(ownerAccountId)
        ?: return AccountSessionRefreshResult.DefinitiveFailure(
            DefinitiveAccountIdentityException("The verified account has no refresh credential."),
        )
    val session = try {
        refreshSession(refreshToken)
    } catch (failure: Throwable) {
        return if (failure.isDefinitiveAccountAuthFailure()) {
            AccountSessionRefreshResult.DefinitiveFailure(failure)
        } else {
            AccountSessionRefreshResult.Retryable(failure)
        }
    }
    val access = session.access.takeIf { it.isNotBlank() }
        ?: return AccountSessionRefreshResult.DefinitiveFailure(
            DefinitiveAccountIdentityException("Authentication returned no access token."),
        )
    val profile = try {
        verifyProfile(access)
    } catch (failure: Throwable) {
        return if (failure.isDefinitiveAccountAuthFailure()) {
            AccountSessionRefreshResult.DefinitiveFailure(failure)
        } else {
            AccountSessionRefreshResult.Retryable(failure)
        }
    }
    if (tokenStore.accountId() != ownerAccountId) return AccountSessionRefreshResult.StaleAccount
    if (profile.id.toString() != ownerAccountId) {
        return AccountSessionRefreshResult.DefinitiveFailure(
            DefinitiveAccountIdentityException(
                "Refreshed credentials do not belong to the stored account.",
            ),
        )
    }
    return if (tokenStore.updateSessionForAccount(ownerAccountId, access, session.refresh)) {
        AccountSessionRefreshResult.Verified
    } else {
        AccountSessionRefreshResult.StaleAccount
    }
}

/**
 * Process-local visibility notification paired with the cross-process Room generation
 * tombstone. Deleting owner rows also empties active Room flows in another process.
 */
object AccountVisibilityInvalidations {
    private val listeners = CopyOnWriteArraySet<(String) -> Unit>()

    fun register(listener: (String) -> Unit) {
        listeners += listener
    }

    fun unregister(listener: (String) -> Unit) {
        listeners -= listener
    }

    internal fun deactivate(ownerAccountId: String) {
        listeners.forEach { listener -> listener(ownerAccountId) }
    }
}

/**
 * The sole destructive account invalidation path used by UI auth, WorkManager, and push.
 * It is idempotent. Room's lifecycle generation makes revocation and purge visible across
 * processes before any later account-bound commit is allowed.
 */
class AccountSessionInvalidator(
    private val database: MedtrackDatabase,
    private val tokenStore: TokenStore,
    private val lockStore: LockStore,
    private val cancelAccountWork: suspend (String) -> Unit,
) {
    constructor(context: Context) : this(
        database = MedtrackDatabase.build(context.applicationContext),
        tokenStore = TokenStore(context.applicationContext),
        lockStore = LockStore(context.applicationContext),
        cancelAccountWork = { accountId ->
            MedtrackSyncWorker.cancelForAccount(context.applicationContext, accountId)
        },
    )

    constructor(
        context: Context,
        database: MedtrackDatabase,
        tokenStore: TokenStore,
        lockStore: LockStore,
    ) : this(
        database = database,
        tokenStore = tokenStore,
        lockStore = lockStore,
        cancelAccountWork = { accountId ->
            MedtrackSyncWorker.cancelForAccount(context.applicationContext, accountId)
        },
    )

    suspend fun invalidate(ownerAccountId: String?) = withContext(NonCancellable) {
        var firstFailure: Throwable? = null
        fun recordFailure(failure: Throwable) {
            if (firstFailure == null) {
                firstFailure = failure
            } else if (firstFailure !== failure) {
                firstFailure?.addSuppressed(failure)
            }
        }
        suspend fun attempt(block: suspend () -> Unit) {
            try {
                block()
            } catch (failure: Throwable) {
                recordFailure(failure)
            }
        }

        val accountId = ownerAccountId?.takeIf { it.isNotBlank() }
        if (accountId == null) {
            attempt { tokenStore.clear() }
            attempt { lockStore.deactivate() }
        } else {
            attempt { cancelAccountWork(accountId) }
            attempt { AccountVisibilityInvalidations.deactivate(accountId) }
            attempt { database.invalidateAndClearAccountData(accountId) }
            // Catch a one-time enqueue that raced the first cancellation while an
            // already-started account commit was draining before the purge transaction.
            attempt { cancelAccountWork(accountId) }
            attempt { lockStore.clearAccount(accountId) }
            attempt { tokenStore.clearForAccount(accountId) }
        }
        firstFailure?.let { throw it }
    }

    suspend fun invalidateIfCurrent(ownerAccountId: String): Boolean {
        if (tokenStore.accountId() != ownerAccountId) return false
        invalidate(ownerAccountId)
        return true
    }
}
