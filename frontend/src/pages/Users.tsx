import React, { useState, useEffect, useCallback } from 'react';
import { 
  UserPlus, Search, UserCheck, RefreshCw, 
  Edit2, UserX, X, AlertTriangle 
} from 'lucide-react';
import { usersApi, type UserItem } from '../api/users';
import { useAuth } from '../context/AuthContext';
import styles from './Users.module.css';

export const Users: React.FC = () => {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<UserItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Modals state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingUser, setEditingUser] = useState<UserItem | null>(null);
  const [deactivatingUser, setDeactivatingUser] = useState<UserItem | null>(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);

  // Form states
  const [newUsername, setNewUsername] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newDisplayName, setNewDisplayName] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState<'ADMIN' | 'USER'>('USER');

  // Edit form states
  const [editDisplayName, setEditDisplayName] = useState('');
  const [editEmail, setEditEmail] = useState('');
  const [editRole, setEditRole] = useState<'ADMIN' | 'USER'>('USER');
  const [editIsActive, setEditIsActive] = useState(true);
  const [editPassword, setEditPassword] = useState('');

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await usersApi.listUsers({
        limit: 100,
        offset: 0,
        search: search.trim() || undefined,
        role: roleFilter || undefined,
        is_active: statusFilter === '' ? undefined : statusFilter === 'true',
      });
      setUsers(data.items);
      setTotal(data.total);
    } catch (err: any) {
      setError(err.message || 'Failed to load users');
    } finally {
      setLoading(false);
    }
  }, [search, roleFilter, statusFilter]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUsername.trim() || !newPassword) {
      setModalError('Username and password are required');
      return;
    }
    if (newPassword.length < 8) {
      setModalError('Password must be at least 8 characters long');
      return;
    }

    setModalLoading(true);
    setModalError(null);
    try {
      await usersApi.createUser({
        username: newUsername.trim(),
        email: newEmail.trim() || undefined,
        display_name: newDisplayName.trim() || undefined,
        password: newPassword,
        role: newRole,
        is_active: true,
      });
      setShowCreateModal(false);
      setNewUsername('');
      setNewEmail('');
      setNewDisplayName('');
      setNewPassword('');
      setNewRole('USER');
      fetchUsers();
    } catch (err: any) {
      setModalError(err.message || 'Failed to create user');
    } finally {
      setModalLoading(false);
    }
  };

  const openEditModal = (target: UserItem) => {
    setEditingUser(target);
    setEditDisplayName(target.display_name || '');
    setEditEmail(target.email || '');
    setEditRole((target.role as 'ADMIN' | 'USER') || 'USER');
    setEditIsActive(target.is_active);
    setEditPassword('');
    setModalError(null);
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingUser) return;

    setModalLoading(true);
    setModalError(null);
    try {
      await usersApi.updateUser(editingUser.id, {
        display_name: editDisplayName.trim() || undefined,
        email: editEmail.trim() || undefined,
        role: editRole,
        is_active: editIsActive,
        password: editPassword || undefined,
      });
      setEditingUser(null);
      fetchUsers();
    } catch (err: any) {
      setModalError(err.message || 'Failed to update user');
    } finally {
      setModalLoading(false);
    }
  };

  const handleDeactivateConfirm = async () => {
    if (!deactivatingUser) return;
    setModalLoading(true);
    setModalError(null);
    try {
      await usersApi.deactivateUser(deactivatingUser.id);
      setDeactivatingUser(null);
      fetchUsers();
    } catch (err: any) {
      setModalError(err.message || 'Failed to deactivate user');
    } finally {
      setModalLoading(false);
    }
  };

  const activeCount = users.filter((u) => u.is_active).length;
  const adminCount = users.filter((u) => u.role === 'ADMIN').length;
  const userCount = users.filter((u) => u.role === 'USER').length;

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerTitle}>
          <h1>User Management</h1>
          <p className={styles.headerSubtitle}>
            Manage sovereign access, RBAC permissions, and engineer credentials
          </p>
        </div>
        <div className={styles.headerActions}>
          <button
            type="button"
            className={styles.refreshBtn}
            onClick={fetchUsers}
            disabled={loading}
            title="Refresh user list"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            <span>Refresh</span>
          </button>
          <button
            type="button"
            className={styles.primaryBtn}
            onClick={() => {
              setShowCreateModal(true);
              setModalError(null);
            }}
          >
            <UserPlus size={16} />
            <span>Create User</span>
          </button>
        </div>
      </div>

      {/* Metrics Cards */}
      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Total Users</span>
          <span className={styles.statValue}>{total}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Active Accounts</span>
          <span className={styles.statValue}>{activeCount}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Administrators</span>
          <span className={styles.statValue}>{adminCount}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Engineers</span>
          <span className={styles.statValue}>{userCount}</span>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className={styles.filterCard}>
        <div className={styles.searchWrapper}>
          <Search size={16} className={styles.searchIcon} />
          <input
            type="text"
            className={styles.searchInput}
            placeholder="Search users by name, username, or email..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className={styles.filterControls}>
          <select
            className={styles.filterSelect}
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            aria-label="Filter by role"
          >
            <option value="">All Roles</option>
            <option value="ADMIN">Administrators</option>
            <option value="USER">Engineers</option>
          </select>
          <select
            className={styles.filterSelect}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label="Filter by status"
          >
            <option value="">All Statuses</option>
            <option value="true">Active</option>
            <option value="false">Deactivated</option>
          </select>
        </div>
      </div>

      {error && <div className={styles.errorBanner}>{error}</div>}

      {/* Users Table */}
      <div className={styles.tableCard}>
        <div className={styles.tableWrapper}>
          <table className={styles.usersTable}>
            <thead>
              <tr>
                <th>User</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th>Created</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 ? (
                <tr>
                  <td colSpan={6} className={styles.emptyState}>
                    {loading ? 'Loading sovereign users...' : 'No users found.'}
                  </td>
                </tr>
              ) : (
                users.map((item) => {
                  const initials = (item.display_name || item.username)
                    .slice(0, 2)
                    .toUpperCase();
                  const isSelf = currentUser?.id === item.id;
                  const isAdminRole = item.role === 'ADMIN';

                  return (
                    <tr key={item.id}>
                      <td>
                        <div className={styles.userCell}>
                          <div
                            className={`${styles.userAvatar} ${
                              isAdminRole ? styles.userAvatarAdmin : ''
                            }`}
                          >
                            {initials}
                          </div>
                          <div className={styles.userInfo}>
                            <span className={styles.userName}>
                              {item.username} {isSelf && '(You)'}
                            </span>
                            {item.display_name && (
                              <span className={styles.userDisplayName}>
                                {item.display_name}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td>{item.email || '—'}</td>
                      <td>
                        <span
                          className={`${styles.roleBadge} ${
                            isAdminRole
                              ? styles.roleBadgeAdmin
                              : styles.roleBadgeUser
                          }`}
                        >
                          {isAdminRole ? 'ADMIN' : 'ENGINEER'}
                        </span>
                      </td>
                      <td>
                        <span
                          className={`${styles.statusPill} ${
                            item.is_active
                              ? styles.statusActive
                              : styles.statusInactive
                          }`}
                        >
                          <span className={styles.statusDot} />
                          {item.is_active ? 'Active' : 'Deactivated'}
                        </span>
                      </td>
                      <td>
                        {item.created_at
                          ? new Date(item.created_at).toLocaleDateString()
                          : '—'}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <div
                          className={styles.actionsCell}
                          style={{ justifyContent: 'flex-end' }}
                        >
                          <button
                            type="button"
                            className={styles.actionBtn}
                            onClick={() => openEditModal(item)}
                            title="Edit user"
                            aria-label={`Edit ${item.username}`}
                          >
                            <Edit2 size={14} />
                          </button>
                          {item.is_active ? (
                            <button
                              type="button"
                              className={`${styles.actionBtn} ${styles.actionBtnDeactivate}`}
                              onClick={() => {
                                setDeactivatingUser(item);
                                setModalError(null);
                              }}
                              disabled={isSelf}
                              title={
                                isSelf
                                  ? 'Cannot deactivate active session'
                                  : 'Soft-deactivate account'
                              }
                              aria-label={`Deactivate ${item.username}`}
                            >
                              <UserX size={14} />
                            </button>
                          ) : (
                            <button
                              type="button"
                              className={styles.actionBtn}
                              onClick={() => {
                                usersApi
                                  .updateUser(item.id, { is_active: true })
                                  .then(() => fetchUsers());
                              }}
                              title="Reactivate account"
                              aria-label={`Reactivate ${item.username}`}
                            >
                              <UserCheck size={14} />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal: Create User */}
      {showCreateModal && (
        <div className={styles.modalOverlay}>
          <div className={styles.modalCard}>
            <div className={styles.modalHeader}>
              <h2>Create New User</h2>
              <button
                type="button"
                className={styles.closeBtn}
                onClick={() => setShowCreateModal(false)}
                aria-label="Close modal"
              >
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleCreateSubmit}>
              <div className={styles.modalBody}>
                {modalError && (
                  <div className={styles.errorBanner}>{modalError}</div>
                )}
                <div className={styles.formGroup}>
                  <label htmlFor="newUsername">Username *</label>
                  <input
                    id="newUsername"
                    type="text"
                    required
                    placeholder="e.g. j_doe"
                    value={newUsername}
                    onChange={(e) => setNewUsername(e.target.value)}
                  />
                </div>
                <div className={styles.formGroup}>
                  <label htmlFor="newDisplayName">Display Name</label>
                  <input
                    id="newDisplayName"
                    type="text"
                    placeholder="e.g. John Doe"
                    value={newDisplayName}
                    onChange={(e) => setNewDisplayName(e.target.value)}
                  />
                </div>
                <div className={styles.formGroup}>
                  <label htmlFor="newEmail">Email</label>
                  <input
                    id="newEmail"
                    type="email"
                    placeholder="e.g. j_doe@mrpl.co.in"
                    value={newEmail}
                    onChange={(e) => setNewEmail(e.target.value)}
                  />
                </div>
                <div className={styles.formGroup}>
                  <label htmlFor="newRole">Role</label>
                  <select
                    id="newRole"
                    value={newRole}
                    onChange={(e) =>
                      setNewRole(e.target.value as 'ADMIN' | 'USER')
                    }
                  >
                    <option value="USER">Engineer (Standard User)</option>
                    <option value="ADMIN">Administrator (Full RBAC)</option>
                  </select>
                </div>
                <div className={styles.formGroup}>
                  <label htmlFor="newPassword">Initial Password *</label>
                  <input
                    id="newPassword"
                    type="password"
                    required
                    placeholder="At least 8 characters"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                  />
                  <span className={styles.formHint}>
                    Password must be at least 8 characters long.
                  </span>
                </div>
              </div>
              <div className={styles.modalFooter}>
                <button
                  type="button"
                  className={styles.secondaryBtn}
                  onClick={() => setShowCreateModal(false)}
                  disabled={modalLoading}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className={styles.primaryBtn}
                  disabled={modalLoading}
                >
                  {modalLoading ? 'Creating...' : 'Create Account'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Edit User */}
      {editingUser && (
        <div className={styles.modalOverlay}>
          <div className={styles.modalCard}>
            <div className={styles.modalHeader}>
              <h2>Edit User ({editingUser.username})</h2>
              <button
                type="button"
                className={styles.closeBtn}
                onClick={() => setEditingUser(null)}
                aria-label="Close modal"
              >
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleEditSubmit}>
              <div className={styles.modalBody}>
                {modalError && (
                  <div className={styles.errorBanner}>{modalError}</div>
                )}
                <div className={styles.formGroup}>
                  <label htmlFor="editDisplayName">Display Name</label>
                  <input
                    id="editDisplayName"
                    type="text"
                    placeholder="Full Name"
                    value={editDisplayName}
                    onChange={(e) => setEditDisplayName(e.target.value)}
                  />
                </div>
                <div className={styles.formGroup}>
                  <label htmlFor="editEmail">Email</label>
                  <input
                    id="editEmail"
                    type="email"
                    placeholder="engineer@mrpl.co.in"
                    value={editEmail}
                    onChange={(e) => setEditEmail(e.target.value)}
                  />
                </div>
                <div className={styles.formGroup}>
                  <label htmlFor="editRole">Role</label>
                  <select
                    id="editRole"
                    value={editRole}
                    disabled={currentUser?.id === editingUser.id}
                    onChange={(e) =>
                      setEditRole(e.target.value as 'ADMIN' | 'USER')
                    }
                  >
                    <option value="USER">Engineer (Standard User)</option>
                    <option value="ADMIN">Administrator (Full RBAC)</option>
                  </select>
                  {currentUser?.id === editingUser.id && (
                    <span className={styles.formHint}>
                      You cannot revoke your own administrator privileges.
                    </span>
                  )}
                </div>
                <div className={styles.formGroup}>
                  <label htmlFor="editStatus">Account Status</label>
                  <select
                    id="editStatus"
                    value={editIsActive ? 'active' : 'inactive'}
                    disabled={currentUser?.id === editingUser.id}
                    onChange={(e) => setEditIsActive(e.target.value === 'active')}
                  >
                    <option value="active">Active</option>
                    <option value="inactive">Deactivated</option>
                  </select>
                  {currentUser?.id === editingUser.id && (
                    <span className={styles.formHint}>
                      You cannot deactivate your own active session.
                    </span>
                  )}
                </div>
                <div className={styles.formGroup}>
                  <label htmlFor="editPassword">Reset Password (Optional)</label>
                  <input
                    id="editPassword"
                    type="password"
                    placeholder="Leave blank to preserve existing password"
                    value={editPassword}
                    onChange={(e) => setEditPassword(e.target.value)}
                  />
                  <span className={styles.formHint}>
                    Only enter a value if resetting credentials (min 8 chars).
                  </span>
                </div>
              </div>
              <div className={styles.modalFooter}>
                <button
                  type="button"
                  className={styles.secondaryBtn}
                  onClick={() => setEditingUser(null)}
                  disabled={modalLoading}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className={styles.primaryBtn}
                  disabled={modalLoading}
                >
                  {modalLoading ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Confirm Deactivation */}
      {deactivatingUser && (
        <div className={styles.modalOverlay}>
          <div className={styles.modalCard}>
            <div className={styles.modalHeader}>
              <h2>Confirm Deactivation</h2>
              <button
                type="button"
                className={styles.closeBtn}
                onClick={() => setDeactivatingUser(null)}
                aria-label="Close modal"
              >
                <X size={18} />
              </button>
            </div>
            <div className={styles.modalBody}>
              {modalError && (
                <div className={styles.errorBanner}>{modalError}</div>
              )}
              <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                <AlertTriangle size={24} color="#f59e0b" style={{ flexShrink: 0, marginTop: '2px' }} />
                <div>
                  <p style={{ margin: '0 0 8px 0', fontWeight: 600, color: 'var(--color-text-strong)' }}>
                    Soft-deactivate account for "{deactivatingUser.username}"?
                  </p>
                  <p style={{ margin: 0, fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)' }}>
                    The user will immediately lose access and be unable to log in. 
                    All existing conversation history, uploaded documents, and files will be safely preserved.
                  </p>
                </div>
              </div>
            </div>
            <div className={styles.modalFooter}>
              <button
                type="button"
                className={styles.secondaryBtn}
                onClick={() => setDeactivatingUser(null)}
                disabled={modalLoading}
              >
                Cancel
              </button>
              <button
                type="button"
                className={styles.primaryBtn}
                style={{ background: 'var(--color-danger-600, #dc2626)', borderColor: 'var(--color-danger-600, #dc2626)' }}
                onClick={handleDeactivateConfirm}
                disabled={modalLoading}
              >
                {modalLoading ? 'Deactivating...' : 'Deactivate Account'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
