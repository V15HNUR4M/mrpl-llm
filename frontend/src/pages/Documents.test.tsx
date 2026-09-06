import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Documents } from './Documents';
import * as documentsApiModule from '../api/documents';

vi.mock('../api/documents', () => ({
  documentsApi: {
    getDocuments: vi.fn(),
    uploadDocument: vi.fn(),
    deleteDocument: vi.fn(),
  },
}));

describe('Documents UI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders document list and empty state', async () => {
    vi.spyOn(documentsApiModule.documentsApi, 'getDocuments').mockResolvedValue([]);
    
    render(<Documents />);
    
    expect(await screen.findByText(/no documents found/i)).toBeInTheDocument();
  });

  it('renders documents and their status', async () => {
    vi.spyOn(documentsApiModule.documentsApi, 'getDocuments').mockResolvedValue([
      { id: '1', filename: 'test1.pdf', status: 'INDEXED', created_at: new Date().toISOString(), file_type: 'application/pdf', file_size: 1024, updated_at: new Date().toISOString() },
      { id: '2', filename: 'test2.txt', status: 'PROCESSING', created_at: new Date().toISOString(), file_type: 'text/plain', file_size: 512, updated_at: new Date().toISOString() },
    ]);
    
    render(<Documents />);
    
    expect(await screen.findByText('test1.pdf')).toBeInTheDocument();
    expect(await screen.findByText('test2.txt')).toBeInTheDocument();
    expect(screen.getByText('INDEXED')).toBeInTheDocument();
    expect(screen.getByText('PROCESSING')).toBeInTheDocument();
  });

  it('handles upload failure gracefully', async () => {
    vi.spyOn(documentsApiModule.documentsApi, 'getDocuments').mockResolvedValue([]);
    vi.spyOn(documentsApiModule.documentsApi, 'uploadDocument').mockRejectedValue(new Error('Upload failed'));
    const alertMock = vi.spyOn(window, 'alert').mockImplementation(() => {});
    
    render(<Documents />);
    
    const fileInput = screen.getByTestId('file-input');
    const file = new File(['hello'], 'hello.pdf', { type: 'application/pdf' });
    
    await act(async () => {
      await userEvent.upload(fileInput, file);
    });

    expect(alertMock).toHaveBeenCalledWith('Upload failed. Please try again.');
  });
});
