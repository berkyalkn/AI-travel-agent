import React from 'react';
import ReactMarkdown from 'react-markdown';

function ReportDisplay({ isLoading, error, report }) {
  if (isLoading) {
    return <div className="loading-spinner"></div>;
  }

  return (
    <main className="report-container">
      {error && <div className="error-box">{error}</div>}
      {report && (
        <div className="markdown-content">
          <ReactMarkdown>{report}</ReactMarkdown>
        </div>
      )}
    </main>
  );
}

export default ReportDisplay;