import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MarkdownRenderer } from './MarkdownRenderer';

describe('MarkdownRenderer Component', () => {
  it('renders paragraphs and headings correctly', () => {
    const md = '# Main Title\n\n## Subtitle\n\nThis is a standard paragraph.';
    render(<MarkdownRenderer content={md} />);
    
    expect(screen.getByRole('heading', { level: 1, name: 'Main Title' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Subtitle' })).toBeInTheDocument();
    expect(screen.getByText('This is a standard paragraph.')).toBeInTheDocument();
  });

  it('renders ordered and unordered lists structurally', () => {
    const md = '- Item 1\n- Item 2\n\n1. First\n2. Second';
    render(<MarkdownRenderer content={md} />);
    
    const lists = screen.getAllByRole('list');
    expect(lists.length).toBe(2);
    expect(screen.getByText('Item 1')).toBeInTheDocument();
    expect(screen.getByText('Item 2')).toBeInTheDocument();
    expect(screen.getByText('First')).toBeInTheDocument();
    expect(screen.getByText('Second')).toBeInTheDocument();
  });

  it('renders inline code and fenced code blocks', () => {
    const md = 'Here is `inline_var` and a block:\n\n```python\nprint("hello world")\n```';
    const { container } = render(<MarkdownRenderer content={md} />);
    
    const inlineCode = container.querySelector('code');
    expect(inlineCode).toBeInTheDocument();
    expect(inlineCode?.textContent).toContain('inline_var');

    const preBlock = container.querySelector('pre code');
    expect(preBlock).toBeInTheDocument();
    expect(preBlock?.textContent).toContain('print("hello world")');
  });

  it('renders tables correctly', () => {
    const md = '| Col 1 | Col 2 |\n|---|---|\n| Val A | Val B |';
    render(<MarkdownRenderer content={md} />);
    
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getByText('Col 1')).toBeInTheDocument();
    expect(screen.getByText('Val A')).toBeInTheDocument();
  });

  it('sanitizes malicious script tags and event handlers (XSS protection)', () => {
    const maliciousMd = '<script>window.pwned = true;</script><img src="x" onerror="alert(1)" />Safe text';
    const { container } = render(<MarkdownRenderer content={maliciousMd} />);
    
    expect(container.querySelector('script')).toBeNull();
    const img = container.querySelector('img');
    if (img) {
      expect(img.getAttribute('onerror')).toBeNull();
    }
    expect(screen.getByText('Safe text')).toBeInTheDocument();
  });

  it('handles streaming/incomplete markdown gracefully', () => {
    const partialMd = '1. First item\n2. ';
    render(<MarkdownRenderer content={partialMd} />);
    expect(screen.getByText('First item')).toBeInTheDocument();
  });
});
