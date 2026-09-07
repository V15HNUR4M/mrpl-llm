import React, { useMemo } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import styles from './MarkdownRenderer.module.css';

// Configure marked with GitHub Flavored Markdown and line breaks
marked.setOptions({
  gfm: true,
  breaks: true,
});

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = React.memo(({ content, className }) => {
  const sanitizedHtml = useMemo(() => {
    if (!content) return '';
    
    try {
      // Parse markdown to HTML synchronously
      const rawHtml = marked.parse(content) as string;
      
      // Sanitize via DOMPurify to eliminate XSS risks
      return DOMPurify.sanitize(rawHtml, {
        USE_PROFILES: { html: true },
        ADD_ATTR: ['target', 'rel'],
      });
    } catch (err) {
      console.error('Failed to parse Markdown:', err);
      return DOMPurify.sanitize(content);
    }
  }, [content]);

  return (
    <div
      className={`${styles.markdownBody} ${className || ''}`}
      dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
    />
  );
});

MarkdownRenderer.displayName = 'MarkdownRenderer';
