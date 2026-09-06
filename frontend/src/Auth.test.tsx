import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter, MemoryRouter } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { Login } from './pages/Login';
import * as authApiModule from './api/auth';

// Mock the API calls
vi.mock('./api/auth', () => ({
  authApi: {
    login: vi.fn(),
    me: vi.fn(),
  },
}));

vi.mock('./api/documents', () => ({
  documentsApi: {
    list: vi.fn().mockResolvedValue([]),
    upload: vi.fn(),
    delete: vi.fn(),
  },
}));

const renderWithRouter = (ui: React.ReactElement, { route = '/' } = {}) => {
  window.history.pushState({}, 'Test page', route);
  return render(ui, { wrapper: BrowserRouter });
};

describe('Authentication Flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders login form and validates', async () => {
    const user = userEvent.setup();
    renderWithRouter(
      <AuthProvider>
        <Login />
      </AuthProvider>
    );

    const heading = screen.getByRole('heading', { name: /mrpl ai workbench/i });
    expect(heading).toBeInTheDocument();

    const loginButton = screen.getByRole('button', { name: /sign in/i });
    
    // Check validation
    await user.click(loginButton);
    expect(screen.getByText(/username and password are required/i)).toBeInTheDocument();
  });

  it('handles successful login', async () => {
    const user = userEvent.setup();
    const mockLogin = vi.spyOn(authApiModule.authApi, 'login').mockResolvedValue({
      access_token: 'fake-token',
      token_type: 'bearer',
      user: { id: '1', username: 'admin', email: 'test@test.com', is_active: true, role: 'ADMIN' }
    });
    vi.spyOn(authApiModule.authApi, 'me').mockResolvedValue({
      id: '1',
      username: 'admin',
      email: 'test@test.com',
      is_active: true,
      role: 'ADMIN',
    });

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <Login />
        </AuthProvider>
      </MemoryRouter>
    );

    await user.type(screen.getByLabelText(/username/i), 'admin');
    await user.type(screen.getByLabelText(/password/i), 'password');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(mockLogin).toHaveBeenCalledWith('admin', 'password');
  });

  it('handles failed login', async () => {
    const user = userEvent.setup();
    vi.spyOn(authApiModule.authApi, 'login').mockRejectedValue(new Error('Invalid credentials'));

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <Login />
        </AuthProvider>
      </MemoryRouter>
    );

    await user.type(screen.getByLabelText(/username/i), 'wronguser');
    await user.type(screen.getByLabelText(/password/i), 'wrong');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByText(/invalid credentials/i)).toBeInTheDocument();
  });
});
