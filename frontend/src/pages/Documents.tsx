import React, { useEffect, useState, useRef } from 'react';
import { UploadCloud, FileText, Trash2, RefreshCw } from 'lucide-react';
import { documentsApi } from '../api/documents';
import type { Document } from '../api/documents';
import styles from './Documents.module.css';

export const Documents: React.FC = () => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchDocuments = async () => {
    try {
      setLoading(true);
      const docs = await documentsApi.getDocuments();
      setDocuments(docs);
    } catch (err) {
      console.error('Failed to fetch documents', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      setUploading(true);
      await documentsApi.uploadDocument(file);
      await fetchDocuments();
    } catch (err) {
      console.error('Upload failed', err);
      alert('Upload failed. Please try again.');
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm('Are you sure you want to delete this document?')) return;
    try {
      await documentsApi.deleteDocument(id);
      setDocuments(docs => docs.filter(d => d.id !== id));
    } catch (err) {
      console.error('Delete failed', err);
      alert('Failed to delete document.');
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString(undefined, { 
      year: 'numeric', month: 'short', day: 'numeric' 
    });
  };

  const getStatusClass = (status: string) => {
    if (status === 'INDEXED') return styles.statusIndexed;
    if (status === 'PROCESSING') return styles.statusProcessing;
    if (status === 'FAILED') return styles.statusFailed;
    return '';
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>Knowledge Base</h1>
        <button 
          className="btn btn-outline"
          onClick={fetchDocuments}
          disabled={loading || uploading}
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      <div 
        className={styles.uploadZone}
        onClick={() => !uploading && fileInputRef.current?.click()}
      >
        <UploadCloud size={32} className={styles.uploadIcon} />
        <div className={styles.uploadText}>
          {uploading ? 'Uploading and processing...' : 'Click or drag file to this area to upload'}
        </div>
        <div className={styles.uploadSubtext}>
          Supports PDF, MD, TXT
        </div>
        <input 
          type="file" 
          ref={fileInputRef} 
          className={styles.hiddenInput} 
          onChange={handleFileChange}
          disabled={uploading}
          accept=".pdf,.md,.txt"
          data-testid="file-input"
        />
      </div>

      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Document</th>
              <th>Status</th>
              <th>Size</th>
              <th>Updated</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && documents.length === 0 ? (
              <tr>
                <td colSpan={5} className={styles.emptyState}>Loading documents...</td>
              </tr>
            ) : documents.length === 0 ? (
              <tr>
                <td colSpan={5} className={styles.emptyState}>No documents found. Upload one to get started.</td>
              </tr>
            ) : (
              documents.map(doc => (
                <tr key={doc.id}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <FileText size={16} color="var(--color-text-muted)" />
                      {doc.filename}
                    </div>
                  </td>
                  <td>
                    <span className={`${styles.statusBadge} ${getStatusClass(doc.status)}`}>
                      {doc.status}
                    </span>
                  </td>
                  <td>{(doc.file_size / 1024).toFixed(1)} KB</td>
                  <td>{formatDate(doc.updated_at)}</td>
                  <td>
                    <button 
                      className="btn btn-outline" 
                      style={{ padding: '4px 8px', color: 'var(--color-status-error)', borderColor: 'transparent' }}
                      onClick={() => handleDelete(doc.id)}
                      title="Delete document"
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
