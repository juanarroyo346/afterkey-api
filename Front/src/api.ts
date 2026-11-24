import AsyncStorage from '@react-native-async-storage/async-storage';

export const API_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000';

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = await AsyncStorage.getItem('afterkey_token');
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.mensaje || body.error || 'No fue posible completar la solicitud');
  }
  return body as T;
}

export type Page<T> = { items: T[]; total: number; limit: number; offset: number };
export type Account = {
  id_activo: number; id_establecimiento: number; establecimiento: string;
  tipo: 'Cuenta' | 'Archivo' | 'Servicio'; nombre_activo: string; notas?: string;
  tiene_credenciales: boolean;
};
export type Beneficiary = {
  id_beneficiario: number; nombre_completo: string; email_contacto: string;
  telefono?: string; parentesco?: string; codigo_acceso?: string;
};
export type Instruction = {
  id_instruccion: number; id_activo: number; nombre_activo: string;
  establecimiento: string; id_beneficiario?: number; beneficiario?: string;
  accion: 'Eliminar' | 'Transferir' | 'Conservar'; detalle?: string;
};
export type Establishment = {
  id_establecimiento: number; nombre_entidad: string; email_soporte_legal: string; sector: string;
};
