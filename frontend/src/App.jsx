import React, { useState, useCallback } from 'react';
import './App.css';

const App = () => {
    const [file, setFile] = useState(null);
    const [fields, setFields] = useState("project_name, client, deadline, summary, total_cost");
    const [prompt, setPrompt] = useState("");
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);

    const onFileChange = (e) => {
        setFile(e.target.files[0]);
        setError(null);
    };

    const handleUpload = async () => {
        if (!file) {
            setError("Please select a file first.");
            return;
        }

        setLoading(true);
        setError(null);
        setResult(null);

        const formData = new FormData();
        formData.append("file", file);
        formData.append("fields", fields);
        if (prompt) {
            formData.append("custom_prompt", prompt);
        }

        try {
            const response = await fetch("http://localhost:8000/api/intake/extract-custom", {
                method: "POST",
                body: formData,
            });

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.detail || "Extraction failed.");
            }

            const data = await response.json();
            setResult(data.extracted);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const copyToClipboard = () => {
        navigator.clipboard.writeText(JSON.stringify(result, null, 2));
        alert("Copied to clipboard!");
    };

    return (
        <div className="app-container">
            <header>
                <h1>BidVault Extract</h1>
                <p>Generalized document analysis for any domain.</p>
            </header>

            <div className="main-grid">
                <div className="card config-card">
                    <div className="input-group">
                        <label>Fields to Extract</label>
                        <input 
                            type="text" 
                            placeholder="e.g., project_id, owner, duration, cost" 
                            value={fields}
                            onChange={(e) => setFields(e.target.value)}
                        />
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginTop: '0.2rem' }}>
                            Separate fields with commas.
                        </span>
                    </div>

                    <div className="input-group">
                        <label>Custom Instructions (Optional)</label>
                        <textarea 
                            rows={4}
                            placeholder="e.g. 'Only extract costs in USD', 'Ignore draft versions'"
                            value={prompt}
                            onChange={(e) => setPrompt(e.target.value)}
                        />
                    </div>

                    <div className="input-group">
                        <label>Document Upload</label>
                        <div className="file-drop" onClick={() => document.getElementById('file-input').click()}>
                            {file ? (
                                <div className="file-info">
                                    <h4 style={{ margin: 0 }}>{file.name}</h4>
                                    <p style={{ margin: '0.5rem 0 0', opacity: 0.6 }}>
                                        {(file.size / 1024 / 1024).toFixed(2)} MB
                                    </p>
                                </div>
                            ) : (
                                <div className="empty-file">
                                    <p>Drop PDF / DOCX here or click to browse</p>
                                </div>
                            )}
                            <input 
                                id="file-input" 
                                type="file" 
                                hidden 
                                onChange={onFileChange}
                                accept=".pdf,.docx,.doc,.txt"
                            />
                        </div>
                    </div>

                    <button 
                        className="btn-primary" 
                        onClick={handleUpload}
                        disabled={loading || !file}
                    >
                        {loading ? <span className="loading-spinner"></span> : "Begin Extraction"}
                    </button>

                    {error && <div style={{ color: '#f87171', marginTop: '1rem', padding: '1rem', background: 'rgba(248,113,113,0.1)', borderRadius: '0.75rem' }}>{error}</div>}
                </div>

                <div className="card results-card">
                    <div className="results-header">
                        <h2>Extraction Results</h2>
                        {result && (
                            <button 
                                onClick={copyToClipboard}
                                style={{ background: 'none', border: '1px solid var(--accent)', color: 'var(--accent)', padding: '4px 10px', borderRadius: '4px', cursor: 'pointer', fontSize: '0.8rem' }}
                            >
                                Copy JSON
                            </button>
                        )}
                    </div>

                    {result ? (
                        <div className="results-list">
                            {Object.entries(result).map(([key, value]) => (
                                <div key={key} className="result-item">
                                    <span className="result-label">{key.replace(/_/g, ' ')}</span>
                                    <div className="result-value">
                                        {Array.isArray(value) ? (
                                            <ul style={{ paddingLeft: '1.2rem', margin: '0.5rem 0' }}>
                                                {value.map((v, i) => <li key={i}>{typeof v === 'object' ? JSON.stringify(v) : v}</li>)}
                                            </ul>
                                        ) : (
                                            typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="empty-state">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                                <polyline points="14 2 14 8 20 8"></polyline>
                                <line x1="16" y1="13" x2="8" y2="13"></line>
                                <line x1="16" y1="17" x2="8" y2="17"></line>
                                <polyline points="10 9 9 9 8 9"></polyline>
                            </svg>
                            <p>Upload a document and click "Begin Extraction" to see the magic happen.</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default App;
