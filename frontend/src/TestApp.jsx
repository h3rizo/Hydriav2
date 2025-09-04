// Composant de test simple pour vérifier que React fonctionne
import React from 'react';

function TestApp() {
  return (
    <div style={{ padding: '2rem', background: '#f0f0f0', minHeight: '100vh' }}>
      <h1 style={{ color: '#333' }}>🚀 Test React App</h1>
      <p>Si vous voyez ce message, React fonctionne correctement !</p>
      <button 
        onClick={() => alert('React fonctionne !')}
        style={{
          padding: '1rem 2rem',
          background: '#007bff',
          color: 'white',
          border: 'none',
          borderRadius: '4px',
          cursor: 'pointer'
        }}
      >
        Tester React
      </button>
    </div>
  );
}

export default TestApp;