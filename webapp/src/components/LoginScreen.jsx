import { useState } from "react";
import { supabase } from "../lib/supabaseClient";

export default function LoginScreen({ onLogin }) {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState(null);
  const [carregando, setCarregando] = useState(false);

  if (!supabase) {
    return (
      <div className="app" style={{ justifyContent: "center", alignItems: "center" }}>
        <div style={{ maxWidth: 360, textAlign: "center" }}>
          <p className="secao-header" style={{ color: "var(--accent)" }}>
            Supabase não configurado
          </p>
          <p style={{ color: "var(--text-2)", fontSize: 12 }}>
            Defina VITE_SUPABASE_URL e VITE_SUPABASE_ANON_KEY em webapp/.env.local
            (veja webapp/.env.example) e reinicie o `npm run dev`.
          </p>
        </div>
      </div>
    );
  }

  async function handleSubmit(evento) {
    evento.preventDefault();
    setErro(null);
    setCarregando(true);
    const { data, error } = await supabase.auth.signInWithPassword({ email, password: senha });
    setCarregando(false);
    if (error) {
      setErro(error.message);
      return;
    }
    onLogin(data.session);
  }

  return (
    <div className="app" style={{ justifyContent: "center", alignItems: "center" }}>
      <form onSubmit={handleSubmit} style={{ width: 280, display: "flex", flexDirection: "column", gap: 12 }}>
        <div className="titulos" style={{ marginBottom: 8, textAlign: "center" }}>
          <p className="eyebrow">FIRE UTILS · BIBLIOTECA</p>
          <h1 style={{ fontSize: 18 }}>Entrar</h1>
        </div>
        <input
          type="email"
          placeholder="E-mail"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          style={{ height: 38, borderRadius: 8, border: "1px solid var(--border)", padding: "0 12px" }}
        />
        <input
          type="password"
          placeholder="Senha"
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
          required
          style={{ height: 38, borderRadius: 8, border: "1px solid var(--border)", padding: "0 12px" }}
        />
        {erro && <p style={{ color: "var(--accent)", fontSize: 11 }}>{erro}</p>}
        <button type="submit" className="botao accent" disabled={carregando}>
          {carregando ? "Entrando..." : "Entrar"}
        </button>
      </form>
    </div>
  );
}
