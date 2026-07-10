import { useEffect, useState } from 'react';
import { EditorPage } from './pages/EditorPage';
import { AlertCircle } from 'lucide-react';

interface User {
  id: string;
  email: string;
  display_name: string;
}

function App() {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchDevToken = async () => {
      try {
        const response = await fetch('http://localhost:8000/auth/token', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
        });

        if (!response.ok) {
          throw new Error('Developer authentication failed.');
        }

        const data = await response.json();
        setToken(data.access_token);
        setUser(data.user);
      } catch (err: any) {
        setError(
          err.message ||
          'Could not reach the CodeVerse API. Make sure the backend server (port 8000) is running.'
        );
      } finally {
        setLoading(false);
      }
    };

    fetchDevToken();
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0b0c10] flex flex-col items-center justify-center gap-4 text-gray-200">
        <div className="spinner !w-8 !h-8 !border-2 !border-t-purple-500" />
        <span className="text-sm font-medium tracking-wide">Loading CodeVerse environment...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#0b0c10] flex flex-col items-center justify-center p-6 text-center">
        <div className="max-w-md p-6 glass-panel flex flex-col items-center gap-4">
          <AlertCircle size={40} className="text-red-400" />
          <h2 className="text-lg font-semibold text-gray-200">Server Connection Error</h2>
          <p className="text-sm text-gray-400 leading-relaxed">
            {error}
          </p>
          <button 
            onClick={() => window.location.reload()} 
            className="btn-primary mt-2"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <EditorPage token={token!} user={user} />
  );
}

export default App;
