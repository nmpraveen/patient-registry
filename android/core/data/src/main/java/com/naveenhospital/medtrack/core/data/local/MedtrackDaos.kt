package com.naveenhospital.medtrack.core.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.paging.PagingSource
import kotlinx.coroutines.flow.Flow

@Dao
interface AccountLifecycleDao {
    @Query("SELECT * FROM account_lifecycle WHERE ownerAccountId = :ownerAccountId LIMIT 1")
    suspend fun lifecycle(ownerAccountId: String): AccountLifecycleEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertLifecycle(lifecycle: AccountLifecycleEntity)
}

@Dao
interface CaseDao {
    @Query("SELECT * FROM cases WHERE ownerAccountId = :ownerAccountId ORDER BY nextTaskDueDate IS NULL, nextTaskDueDate ASC, patientName ASC")
    fun observeCases(ownerAccountId: String): Flow<List<CaseEntity>>

    @Query("SELECT * FROM cases WHERE ownerAccountId = :ownerAccountId ORDER BY nextTaskDueDate IS NULL, nextTaskDueDate ASC, patientName ASC")
    fun pagingSource(ownerAccountId: String): PagingSource<Int, CaseEntity>

    @Query("SELECT * FROM cases WHERE ownerAccountId = :ownerAccountId AND id = :caseId LIMIT 1")
    fun observeCase(ownerAccountId: String, caseId: String): Flow<CaseEntity?>

    @Query("SELECT * FROM cases WHERE ownerAccountId = :ownerAccountId AND id = :caseId LIMIT 1")
    suspend fun caseById(ownerAccountId: String, caseId: String): CaseEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertCase(caseEntity: CaseEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertCases(cases: List<CaseEntity>)

    @Query("DELETE FROM cases WHERE ownerAccountId = :ownerAccountId")
    suspend fun clearCases(ownerAccountId: String)
}

@Dao
interface CaseStatsDao {
    @Query("SELECT * FROM case_stats WHERE ownerAccountId = :ownerAccountId AND cacheKey = :cacheKey LIMIT 1")
    suspend fun statsForKey(ownerAccountId: String, cacheKey: String): CaseStatsEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertStats(stats: CaseStatsEntity)
    @Query("DELETE FROM case_stats WHERE ownerAccountId = :ownerAccountId")
    suspend fun clearForOwner(ownerAccountId: String)
}

@Dao
interface TaskDao {
    @Query("SELECT * FROM tasks WHERE ownerAccountId = :ownerAccountId AND caseId = :caseId ORDER BY dueDate IS NULL, dueDate ASC, id ASC")
    fun observeTasksForCase(ownerAccountId: String, caseId: String): Flow<List<TaskEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertTask(task: TaskEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertTasks(tasks: List<TaskEntity>)

    @Query(
        """
        UPDATE tasks
        SET status = 'COMPLETED',
            statusLabel = 'Completed',
            canComplete = 0,
            updatedAtMillis = :updatedAtMillis
        WHERE ownerAccountId = :ownerAccountId AND id = :taskId
        """,
    )
    suspend fun markTaskCompletedLocally(ownerAccountId: String, taskId: String, updatedAtMillis: Long)

    @Query("DELETE FROM tasks WHERE ownerAccountId = :ownerAccountId AND caseId = :caseId")
    suspend fun clearTasksForCase(ownerAccountId: String, caseId: String)

    @Query("DELETE FROM tasks WHERE ownerAccountId = :ownerAccountId")
    suspend fun clearForOwner(ownerAccountId: String)
}

@Dao
interface VitalDao {
    @Query("SELECT * FROM vitals WHERE ownerAccountId = :ownerAccountId AND caseId = :caseId ORDER BY recordedAt DESC, id DESC")
    fun observeVitalsForCase(ownerAccountId: String, caseId: String): Flow<List<VitalEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertVital(vital: VitalEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertVitals(vitals: List<VitalEntity>)

    @Query("DELETE FROM vitals WHERE ownerAccountId = :ownerAccountId AND id = :vitalId")
    suspend fun deleteVital(ownerAccountId: String, vitalId: String)

    @Query("DELETE FROM vitals WHERE ownerAccountId = :ownerAccountId AND caseId = :caseId")
    suspend fun clearVitalsForCase(ownerAccountId: String, caseId: String)

    @Query("DELETE FROM vitals WHERE ownerAccountId = :ownerAccountId")
    suspend fun clearForOwner(ownerAccountId: String)
}

@Dao
interface VitalsThresholdDao {
    @Query("SELECT * FROM vitals_thresholds WHERE ownerAccountId = :ownerAccountId AND id = 'current' LIMIT 1")
    suspend fun currentThresholds(ownerAccountId: String): VitalsThresholdEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertThresholds(thresholds: VitalsThresholdEntity)
    @Query("DELETE FROM vitals_thresholds WHERE ownerAccountId = :ownerAccountId")
    suspend fun clearForOwner(ownerAccountId: String)
}

@Dao
interface CategoryOptionsDao {
    @Query("SELECT * FROM category_options WHERE ownerAccountId = :ownerAccountId AND id = 'current' LIMIT 1")
    suspend fun currentOptions(ownerAccountId: String): CategoryOptionsEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertOptions(options: CategoryOptionsEntity)
    @Query("DELETE FROM category_options WHERE ownerAccountId = :ownerAccountId")
    suspend fun clearForOwner(ownerAccountId: String)
}

@Dao
interface NotificationDao {
    @Query("SELECT * FROM notifications WHERE ownerAccountId = :ownerAccountId ORDER BY createdAt DESC")
    fun observeNotifications(ownerAccountId: String): Flow<List<NotificationEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertNotifications(notifications: List<NotificationEntity>)

    @Query("UPDATE notifications SET isRead = 1 WHERE ownerAccountId = :ownerAccountId AND id = :notificationId")
    suspend fun markRead(ownerAccountId: String, notificationId: String)

    @Query("DELETE FROM notifications WHERE ownerAccountId = :ownerAccountId")
    suspend fun clearForOwner(ownerAccountId: String)

    @Query("DELETE FROM notifications WHERE ownerAccountId = :ownerAccountId")
    suspend fun clearNotifications(ownerAccountId: String)

    @Query("DELETE FROM notifications WHERE ownerAccountId = :ownerAccountId AND type = :type")
    suspend fun clearNotificationsByType(ownerAccountId: String, type: String)
}

@Dao
interface PushTokenDao {
    @Query("SELECT * FROM push_tokens WHERE ownerAccountId = :ownerAccountId AND syncedAtMillis <= 0 ORDER BY token ASC")
    suspend fun pendingTokens(ownerAccountId: String): List<PushTokenEntity>

    @Query("SELECT * FROM push_tokens WHERE ownerAccountId = :ownerAccountId AND syncedAtMillis > 0 ORDER BY syncedAtMillis DESC LIMIT 1")
    suspend fun latestSyncedToken(ownerAccountId: String): PushTokenEntity?

    @Query("SELECT * FROM push_tokens WHERE ownerAccountId = :ownerAccountId ORDER BY syncedAtMillis DESC, token ASC LIMIT 1")
    suspend fun latestToken(ownerAccountId: String): PushTokenEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertToken(token: PushTokenEntity)

    @Query("UPDATE push_tokens SET syncedAtMillis = :syncedAtMillis WHERE ownerAccountId = :ownerAccountId AND token = :token")
    suspend fun markTokenSynced(ownerAccountId: String, token: String, syncedAtMillis: Long)

    @Query("DELETE FROM push_tokens WHERE ownerAccountId = :ownerAccountId AND token = :token")
    suspend fun deleteToken(ownerAccountId: String, token: String)

    @Query("DELETE FROM push_tokens WHERE ownerAccountId = :ownerAccountId")
    suspend fun clearForOwner(ownerAccountId: String)
}

@Dao
interface PendingWriteDao {
    @Query("SELECT * FROM pending_writes WHERE ownerAccountId = :ownerAccountId ORDER BY createdAtMillis ASC")
    suspend fun pendingWrites(ownerAccountId: String): List<PendingWriteEntity>

    @Query("SELECT COUNT(*) FROM pending_writes WHERE ownerAccountId = :ownerAccountId")
    fun observePendingWriteCount(ownerAccountId: String): Flow<Int>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertPendingWrite(write: PendingWriteEntity)

    @Query(
        """
        UPDATE pending_writes
        SET retryCount = retryCount + 1,
            lastError = :lastError,
            updatedAtMillis = :updatedAtMillis
        WHERE ownerAccountId = :ownerAccountId AND clientWriteId = :clientWriteId
        """,
    )
    suspend fun markAttempt(ownerAccountId: String, clientWriteId: String, lastError: String?, updatedAtMillis: Long)

    @Query("DELETE FROM pending_writes WHERE ownerAccountId = :ownerAccountId AND clientWriteId = :clientWriteId")
    suspend fun deletePendingWrite(ownerAccountId: String, clientWriteId: String)

    @Query("DELETE FROM pending_writes WHERE ownerAccountId = :ownerAccountId")
    suspend fun clearForOwner(ownerAccountId: String)

    @Query("DELETE FROM pending_writes WHERE ownerAccountId = :ownerAccountId AND writeType = :writeType")
    suspend fun deletePendingWritesByType(ownerAccountId: String, writeType: String)
}

@Dao
interface SyncConflictDao {
    @Query("SELECT * FROM sync_conflicts WHERE ownerAccountId = :ownerAccountId ORDER BY createdAtMillis DESC")
    fun observeConflicts(ownerAccountId: String): Flow<List<SyncConflictEntity>>

    @Query("SELECT COUNT(*) FROM sync_conflicts WHERE ownerAccountId = :ownerAccountId")
    fun observeConflictCount(ownerAccountId: String): Flow<Int>

    @Query("SELECT * FROM sync_conflicts WHERE ownerAccountId = :ownerAccountId AND clientWriteId = :clientWriteId LIMIT 1")
    suspend fun conflictById(ownerAccountId: String, clientWriteId: String): SyncConflictEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertConflict(conflict: SyncConflictEntity)

    @Query("DELETE FROM sync_conflicts WHERE ownerAccountId = :ownerAccountId AND clientWriteId = :clientWriteId")
    suspend fun deleteConflict(ownerAccountId: String, clientWriteId: String)

    @Query("DELETE FROM sync_conflicts WHERE ownerAccountId = :ownerAccountId")
    suspend fun clearForOwner(ownerAccountId: String)
}

@Dao
interface CacheMetadataDao {
    @Query("SELECT updatedAtMillis FROM cache_metadata WHERE ownerAccountId = :ownerAccountId AND cacheKey = :cacheKey LIMIT 1")
    suspend fun updatedAtMillis(ownerAccountId: String, cacheKey: String): Long?

    @Query("SELECT cacheKey FROM cache_metadata WHERE ownerAccountId = :ownerAccountId AND cacheKey LIKE :prefix || '%'")
    suspend fun cacheKeysStartingWith(ownerAccountId: String, prefix: String): List<String>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertMetadata(metadata: CacheMetadataEntity)
    @Query("DELETE FROM cache_metadata WHERE ownerAccountId = :ownerAccountId")
    suspend fun clearForOwner(ownerAccountId: String)

    @Query("DELETE FROM cache_metadata WHERE ownerAccountId = :ownerAccountId AND cacheKey LIKE :prefix || '%'")
    suspend fun deleteKeysStartingWith(ownerAccountId: String, prefix: String)
}
