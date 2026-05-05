import React, { createContext, useContext, useEffect, useState } from "react";
import { apiGetMe, clearToken, getToken, setToken, type AdminUser } from "../lib/api";

interface AuthState {
    user: AdminUser | null;
    token: string | null;
    loading: boolean;
    login: (token: string) => Promise<void>;
    logout: () => void;
}

const AuthContext = createContext<AuthState>(null!);

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState<AdminUser | null>(null);
    const [token, setTokenState] = useState<string | null>(getToken);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!token) {
            setLoading(false);
            return;
        }
        apiGetMe()
            .then((u) => {
                if (u.role !== "admin") {
                    clearToken();
                    setTokenState(null);
                    setUser(null);
                } else {
                    setUser(u);
                }
            })
            .catch(() => {
                clearToken();
                setTokenState(null);
            })
            .finally(() => setLoading(false));
    }, [token]);

    const login = async (t: string) => {
        setToken(t);
        setTokenState(t);
        const u = await apiGetMe();
        if (u.role !== "admin") {
            clearToken();
            setTokenState(null);
            throw new Error("Access denied: admin role required.");
        }
        setUser(u);
    };

    const logout = () => {
        clearToken();
        setTokenState(null);
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ user, token, loading, login, logout }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    return useContext(AuthContext);
}
