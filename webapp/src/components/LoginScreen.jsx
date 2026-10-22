import { useState } from "react";
import { supabase } from "../lib/supabaseClient";
import Icon from "./Icon";
import Loader from "./Loader";
import checkIconSvg from "../assets/icons/check-icon.svg?raw";
import xIconSvg from "../assets/icons/x-icon.svg?raw";

/**
 * Mesmo layout da tela de login do site (ETOS.FireUtils,
 * src/pages/LoginPage.jsx/.css) — especificamente a variante estreita
 * dela (@media max-width:700px lá), onde a rede de módulos decorativa
 * ao lado some e sobra só o cartão centralizado: é a mesma largura que
 * a dockpane sempre tem. Sempre escura, independente do tema claro/
 * escuro da dockpane (useTema.js) — mesma identidade fixa que a página
 * de login do site tem, isolada da paleta clara/escura do resto da
 * plataforma (ver comentário "landing possui identidade escura
 * própria" em index.css lá).
 */
export default function LoginScreen({ onLogin }) {
  const [modo, setModo] = useState("entrar"); // "entrar" | "cadastro"
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [carregando, setCarregando] = useState(false);
  const [mensagem, setMensagem] = useState(null); // { tipo: "erro" | "sucesso", texto }

  if (!supabase) {
    return (
      <div className="login-tela">
        <div className="login-cartao">
          <h1 className="login-titulo" style={{ color: "var(--accent)" }}>
            Supabase não configurado
          </h1>
          <p className="login-subtitulo">
            Defina VITE_SUPABASE_URL e VITE_SUPABASE_ANON_KEY em webapp/.env.local
            (veja webapp/.env.example) e reinicie o `npm run dev`.
          </p>
        </div>
      </div>
    );
  }

  const entrando = modo === "entrar";

  async function handleSubmit(evento) {
    evento.preventDefault();
    setMensagem(null);
    setCarregando(true);
    try {
      if (entrando) {
        const { data, error } = await supabase.auth.signInWithPassword({ email, password: senha });
        if (error) {
          setMensagem({ tipo: "erro", texto: error.message });
          return;
        }
        onLogin(data.session);
      } else {
        const { data, error } = await supabase.auth.signUp({ email, password: senha });
        if (error) {
          setMensagem({ tipo: "erro", texto: error.message });
          return;
        }
        if (data.session) {
          onLogin(data.session);
        } else {
          setMensagem({ tipo: "sucesso", texto: "Conta criada! Verifique seu e-mail para confirmar antes de entrar." });
        }
      }
    } catch {
      setMensagem({ tipo: "erro", texto: "Não foi possível conectar. Tente novamente em instantes." });
    } finally {
      setCarregando(false);
    }
  }

  function alternarModo() {
    setModo((atual) => (atual === "entrar" ? "cadastro" : "entrar"));
    setMensagem(null);
  }

  const erro = mensagem?.tipo === "erro";

  return (
    <div className="login-tela">
      <div className="login-cartao">
        {carregando && entrando && (
          <div className="login-cartao-loader" role="status" aria-live="polite" aria-label="Entrando">
            <Loader size={40} />
          </div>
        )}

        <h1 className="login-titulo">{entrando ? "Entrar" : "Criar conta"}</h1>
        <p className="login-subtitulo">{entrando ? "Acesse seus projetos." : "Comece a usar o Fire Utils."}</p>

        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-campo">
            <label htmlFor="login-email">E-mail</label>
            <input
              id="login-email"
              type="email"
              placeholder=" "
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div className="login-campo">
            <label htmlFor="login-senha">Senha</label>
            <input
              id="login-senha"
              type="password"
              placeholder=" "
              required
              minLength={6}
              autoComplete={entrando ? "current-password" : "new-password"}
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
            />
          </div>

          {mensagem && (
            <div className={`login-aviso ${erro ? "login-aviso-erro" : "login-aviso-sucesso"}`} role={erro ? "alert" : "status"}>
              <Icon svg={erro ? xIconSvg : checkIconSvg} />
              <span>{mensagem.texto}</span>
            </div>
          )}

          <button type="submit" className="login-botao" disabled={carregando}>
            {carregando ? "Aguarde…" : entrando ? "Entrar" : "Criar conta"}
          </button>
        </form>

        <button type="button" className="login-alternar" onClick={alternarModo} disabled={carregando}>
          {entrando ? "Não tem conta? Criar uma" : "Já tem conta? Entrar"}
        </button>
      </div>
    </div>
  );
}
