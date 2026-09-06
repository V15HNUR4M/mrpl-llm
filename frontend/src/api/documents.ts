import { fetchClient } from './client';

export interface Document {
  id: string;
  filename: string;
  status: 'PROCESSING' | 'INDEXED' | 'FAILED';
  file_type: string;
  file_size: number;
  created_at: string;
  updated_at: string;
}

export interface IngestionResult {
  document_id: string;
  document_version_id: string;
  status: string;
  chunks_processed: number;
  message: string;
}

export const documentsApi = {
  getDocuments: (): Promise<Document[]> => fetchClient<Document[]>('/knowledge/documents'),
  
  uploadDocument: (file: File): Promise<IngestionResult> => {
    const formData = new FormData();
    formData.append('file', file);
    return fetchClient<IngestionResult>('/knowledge/documents', {
      method: 'POST',
      body: formData
    });
  },
  
  deleteDocument: (id: string): Promise<void> => 
    fetchClient<void>(`/knowledge/documents/${id}`, { method: 'DELETE' })
};
