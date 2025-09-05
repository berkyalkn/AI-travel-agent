import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';

function ReportDisplay({ isLoading, error, report }) {
  if (isLoading) {
    return <div className="loading-spinner"></div>;
  }

  if (error) {
    return <div className="error-box">{error}</div>;
  }

  if (report && typeof report === 'string') {
    return (
      <main className="report-container">
        <div className="markdown-content">
          <ReactMarkdown 
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeRaw]}
            >
            {report}
          </ReactMarkdown>
        
        </div>
      </main>
    );
  }
  
  return null;
}

export default ReportDisplay;