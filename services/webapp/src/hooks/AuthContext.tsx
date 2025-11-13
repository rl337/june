import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

interface User {
    id: string;
    username: string;
    token: string;
    role?: string;
    isAdmin?: boolean;
}

interface AuthContextType {
    user: User | null;
    isAuthenticated: boolean;
    isAdmin: boolean;
    login: (username: string) => Promise<void>;
    adminLogin: (adminData: User) => Promise<void>;
    logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [isAdmin, setIsAdminUser] = useState(false);

    useEffect(() => {
        // Check for stored authentication (regular user or admin)
        const storedUser = localStorage.getItem('june_user');
        const storedAdmin = localStorage.getItem('june_admin');
        
        if (storedAdmin) {
            // Admin session takes precedence
            const adminData = JSON.parse(storedAdmin);
            setUser(adminData);
            setIsAuthenticated(true);
            setIsAdminUser(true);
        } else if (storedUser) {
            const userData = JSON.parse(storedUser);
            setUser(userData);
            setIsAuthenticated(true);
            setIsAdminUser(userData.isAdmin || userData.role === 'admin' || false);
        }
    }, []);

    const login = async (username: string) => {
        try {
            const response = await axios.post(`${process.env.REACT_APP_GATEWAY_URL || 'http://localhost:8000'}/auth/token`, null, {
                params: { user_id: username }
            });

            const userData: User = {
                id: username,
                username: username,
                token: response.data.access_token,
                role: response.data.role,
                isAdmin: response.data.role === 'admin' || false
            };

            setUser(userData);
            setIsAuthenticated(true);
            setIsAdminUser(userData.isAdmin || false);
            localStorage.setItem('june_user', JSON.stringify(userData));
            // Clear admin session if switching to regular user
            localStorage.removeItem('june_admin');
        } catch (error) {
            console.error('Login failed:', error);
            throw error;
        }
    };

    const adminLogin = async (adminData: User) => {
        setUser(adminData);
        setIsAuthenticated(true);
        setIsAdminUser(true);
        // Clear regular user session if switching to admin
        localStorage.removeItem('june_user');
    };

    const logout = () => {
        setUser(null);
        setIsAuthenticated(false);
        setIsAdminUser(false);
        localStorage.removeItem('june_user');
        localStorage.removeItem('june_admin');
    };

    return (
        <AuthContext.Provider value={{ user, isAuthenticated, isAdmin, login, adminLogin, logout }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
}
