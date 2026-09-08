import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { Users } from './Users';
import { usersApi } from '../api/users';
import { AuthProvider } from '../context/AuthContext';

vi.mock('../api/users', () => ({
  usersApi: {
    listUsers: vi.fn(),
    createUser: vi.fn(),
    updateUser: vi.fn(),
    deactivateUser: vi.fn(),
  },
}));

const mockUsersData = {
  items: [
    {
      id: 'usr_admin_1',
      username: 'admin',
      email: 'admin@mrpl.co.in',
      display_name: 'System Administrator',
      role: 'ADMIN',
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    {
      id: 'usr_eng_2',
      username: 'engineer1',
      email: 'eng1@mrpl.co.in',
      display_name: 'Process Engineer 1',
      role: 'USER',
      is_active: true,
      created_at: '2026-01-02T00:00:00Z',
      updated_at: '2026-01-02T00:00:00Z',
    },
  ],
  total: 2,
  limit: 100,
  offset: 0,
};

describe('Users Page Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (usersApi.listUsers as any).mockResolvedValue(mockUsersData);
  });

  it('renders user management header and metrics', async () => {
    render(
      <AuthProvider>
        <Users />
      </AuthProvider>
    );

    expect(screen.getByText('User Management')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('admin')).toBeInTheDocument();
      expect(screen.getByText('engineer1')).toBeInTheDocument();
    });
  });

  it('renders role badges for admin and engineer', async () => {
    render(
      <AuthProvider>
        <Users />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('ADMIN')).toBeInTheDocument();
      expect(screen.getByText('ENGINEER')).toBeInTheDocument();
    });
  });
});
