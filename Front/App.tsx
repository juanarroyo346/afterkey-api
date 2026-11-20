import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator, Alert, FlatList, Modal, SafeAreaView, ScrollView,
  StatusBar, StyleSheet, Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons } from '@expo/vector-icons';
import { Account, api, Beneficiary, Establishment, Instruction, Page } from './src/api';

type Tab = 'cuentas' | 'responsables' | 'instrucciones' | 'perfil';

const colors = { ink: '#17221B', green: '#1E6B47', mint: '#DCEADF', cream: '#F7F7F2', white: '#FFFFFF', line: '#DEE5DE', muted: '#69766E', red: '#A63D40' };

export default function App() {
  const [tokenReady, setTokenReady] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('cuentas');

  useEffect(() => { AsyncStorage.getItem('afterkey_token').then((value) => { setToken(value); setTokenReady(true); }); }, []);

  if (!tokenReady) return <View style={[styles.center, { backgroundColor: colors.cream }]}><ActivityIndicator color={colors.green} /></View>;
  if (!token) return <Auth onLogin={async (value) => { await AsyncStorage.setItem('afterkey_token', value); setToken(value); }} />;

  const logout = async () => {
    try { await api('/auth/logout', { method: 'POST', body: '{}' }); } catch {}
    await AsyncStorage.removeItem('afterkey_token');
    setToken(null);
  };

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="dark-content" />
      <View style={styles.header}>
        <View><Text style={styles.eyebrow}>AFTERKEY</Text><Text style={styles.title}>Mi legado digital</Text></View>
        <TouchableOpacity style={styles.iconButton} onPress={logout}><Ionicons name="log-out-outline" size={21} color={colors.ink} /></TouchableOpacity>
      </View>
      <View style={styles.content}>
        {tab === 'cuentas' && <Accounts />}
        {tab === 'responsables' && <Beneficiaries />}
        {tab === 'instrucciones' && <Instructions />}
        {tab === 'perfil' && <Profile />}
      </View>
      <View style={styles.tabs}>
        <TabButton icon="albums-outline" label="Cuentas" active={tab === 'cuentas'} onPress={() => setTab('cuentas')} />
        <TabButton icon="people-outline" label="Responsables" active={tab === 'responsables'} onPress={() => setTab('responsables')} />
        <TabButton icon="document-text-outline" label="Instrucciones" active={tab === 'instrucciones'} onPress={() => setTab('instrucciones')} />
        <TabButton icon="person-outline" label="Perfil" active={tab === 'perfil'} onPress={() => setTab('perfil')} />
      </View>
    </SafeAreaView>
  );
}

function Auth({ onLogin }: { onLogin: (token: string) => Promise<void> }) {
  const [register, setRegister] = useState(false);
  const [name, setName] = useState(''); const [email, setEmail] = useState(''); const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false); const [error, setError] = useState('');
  const submit = async () => {
    setError(''); setLoading(true);
    try {
      if (register) await api('/auth/register', { method: 'POST', body: JSON.stringify({ nombre_completo: name, email, password }) });
      const data = await api<{ access_token: string }>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
      await onLogin(data.access_token);
    } catch (e) { setError(e instanceof Error ? e.message : 'Error de conexión'); }
    finally { setLoading(false); }
  };
  return <SafeAreaView style={styles.authSafe}><StatusBar barStyle="dark-content" /><View style={styles.brandMark}><Ionicons name="key-outline" size={30} color={colors.white} /></View>
    <Text style={styles.authTitle}>{register ? 'Crea tu legado' : 'Bienvenido a AfterKey'}</Text>
    <Text style={styles.authCopy}>{register ? 'Protege tus activos digitales y decide quién debe cuidarlos.' : 'Ingresa para administrar tus cuentas digitales.'}</Text>
    <View style={styles.authForm}>
      {register && <TextInput placeholder="Nombre completo" value={name} onChangeText={setName} style={styles.input} placeholderTextColor={colors.muted} />}
      <TextInput placeholder="Correo electrónico" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" style={styles.input} placeholderTextColor={colors.muted} />
      <TextInput placeholder="Contraseña" value={password} onChangeText={setPassword} secureTextEntry style={styles.input} placeholderTextColor={colors.muted} />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <TouchableOpacity style={styles.primaryButton} onPress={submit} disabled={loading}>{loading ? <ActivityIndicator color={colors.white} /> : <Text style={styles.primaryText}>{register ? 'Crear cuenta' : 'Ingresar'}</Text>}</TouchableOpacity>
      <TouchableOpacity onPress={() => { setRegister(!register); setError(''); }}><Text style={styles.linkText}>{register ? 'Ya tengo una cuenta' : 'Crear una cuenta nueva'}</Text></TouchableOpacity>
    </View>
  </SafeAreaView>;
}

function TabButton({ icon, label, active, onPress }: { icon: any; label: string; active: boolean; onPress: () => void }) {
  return <TouchableOpacity style={styles.tabButton} onPress={onPress}><Ionicons name={icon} size={21} color={active ? colors.green : colors.muted} /><Text style={[styles.tabLabel, active && { color: colors.green }]}>{label}</Text></TouchableOpacity>;
}

function Accounts() {
  const [items, setItems] = useState<Account[]>([]); const [loading, setLoading] = useState(true); const [open, setOpen] = useState(false);
  const [establishments, setEstablishments] = useState<Establishment[]>([]); const [est, setEst] = useState(''); const [name, setName] = useState(''); const [type, setType] = useState<'Cuenta'|'Archivo'|'Servicio'>('Cuenta');
  const load = async () => { setLoading(true); try { const data = await api<Page<Account>>('/accounts'); setItems(data.items); } catch (e) { Alert.alert('Error', String(e)); } finally { setLoading(false); } };
  useEffect(() => { load(); api<Page<Establishment>>('/establishments').then((d) => setEstablishments(d.items)).catch(() => {}); }, []);
  const create = async () => { if (!est || !name) return Alert.alert('Completa los datos', 'Selecciona una entidad y escribe un nombre'); try { await api('/accounts', { method: 'POST', body: JSON.stringify({ id_establecimiento: Number(est), tipo: type, nombre_activo: name }) }); setOpen(false); setName(''); setEst(''); load(); } catch (e) { Alert.alert('Error', String(e)); } };
  const remove = (item: Account) => Alert.alert('Eliminar cuenta', `¿Eliminar ${item.nombre_activo}?`, [{ text: 'Cancelar', style: 'cancel' }, { text: 'Eliminar', style: 'destructive', onPress: async () => { await api(`/accounts/${item.id_activo}`, { method: 'DELETE' }); load(); } }]);
  return <><ScreenHeading title="Cuentas digitales" count={items.length} onAdd={() => setOpen(true)} />
    {loading ? <ActivityIndicator color={colors.green} /> : <FlatList data={items} keyExtractor={(item) => String(item.id_activo)} contentContainerStyle={styles.list} renderItem={({ item }) => <View style={styles.card}><View style={styles.cardIcon}><Ionicons name={item.tipo === 'Archivo' ? 'folder-outline' : 'globe-outline'} size={20} color={colors.green} /></View><View style={styles.cardBody}><Text style={styles.cardTitle}>{item.nombre_activo}</Text><Text style={styles.cardMeta}>{item.establecimiento} · {item.tipo}</Text></View><TouchableOpacity onPress={() => remove(item)}><Ionicons name="trash-outline" size={20} color={colors.red} /></TouchableOpacity></View>} ListEmptyComponent={<Empty text="Aún no tienes cuentas registradas" />} />}
    <Modal visible={open} transparent animationType="slide"><View style={styles.modalWrap}><View style={styles.modal}><Text style={styles.modalTitle}>Nueva cuenta digital</Text><ScrollView><Text style={styles.label}>Entidad</Text>{establishments.map((e) => <TouchableOpacity key={e.id_establecimiento} style={[styles.choice, est === String(e.id_establecimiento) && styles.choiceActive]} onPress={() => setEst(String(e.id_establecimiento))}><Text style={est === String(e.id_establecimiento) ? styles.choiceTextActive : styles.choiceText}>{e.nombre_entidad}</Text></TouchableOpacity>)}<Text style={styles.label}>Nombre</Text><TextInput value={name} onChangeText={setName} placeholder="Ej. Cuenta principal" style={styles.input} /><Text style={styles.label}>Tipo</Text><View style={styles.segment}>{(['Cuenta','Archivo','Servicio'] as const).map((v) => <TouchableOpacity key={v} style={[styles.segmentItem, type === v && styles.segmentActive]} onPress={() => setType(v)}><Text style={type === v ? styles.segmentTextActive : styles.segmentText}>{v}</Text></TouchableOpacity>)}</View><TouchableOpacity style={styles.primaryButton} onPress={create}><Text style={styles.primaryText}>Guardar cuenta</Text></TouchableOpacity><TouchableOpacity style={styles.cancelButton} onPress={() => setOpen(false)}><Text style={styles.cancelText}>Cancelar</Text></TouchableOpacity></ScrollView></View></View></Modal>
  </>;
}

function Beneficiaries() {
  const [items, setItems] = useState<Beneficiary[]>([]); const [loading, setLoading] = useState(true); const [open, setOpen] = useState(false);
  const [name, setName] = useState(''); const [email, setEmail] = useState(''); const [relation, setRelation] = useState('');
  const load = async () => { setLoading(true); try { setItems((await api<Page<Beneficiary>>('/beneficiaries')).items); } catch (e) { Alert.alert('Error', String(e)); } finally { setLoading(false); } };
  useEffect(() => { load(); }, []);
  const create = async () => { try { const data = await api<Beneficiary & { codigo_acceso: string }>('/beneficiaries', { method: 'POST', body: JSON.stringify({ nombre_completo: name, email_contacto: email, parentesco: relation }) }); setOpen(false); setName(''); setEmail(''); setRelation(''); load(); Alert.alert('Código de acceso', `Entrega este código una sola vez al responsable:\n\n${data.codigo_acceso}`); } catch (e) { Alert.alert('Error', String(e)); } };
  const remove = (item: Beneficiary) => Alert.alert('Eliminar responsable', `¿Eliminar a ${item.nombre_completo}?`, [{ text: 'Cancelar' }, { text: 'Eliminar', style: 'destructive', onPress: async () => { try { await api(`/beneficiaries/${item.id_beneficiario}`, { method: 'DELETE' }); load(); } catch (e) { Alert.alert('Error', String(e)); } } }]);
  return <><ScreenHeading title="Responsables" count={items.length} onAdd={() => setOpen(true)} />{loading ? <ActivityIndicator color={colors.green} /> : <FlatList data={items} keyExtractor={(item) => String(item.id_beneficiario)} contentContainerStyle={styles.list} renderItem={({ item }) => <View style={styles.card}><View style={styles.avatar}><Text style={styles.avatarText}>{item.nombre_completo.charAt(0).toUpperCase()}</Text></View><View style={styles.cardBody}><Text style={styles.cardTitle}>{item.nombre_completo}</Text><Text style={styles.cardMeta}>{item.email_contacto}</Text>{item.parentesco ? <Text style={styles.cardMeta}>{item.parentesco}</Text> : null}</View><TouchableOpacity onPress={() => remove(item)}><Ionicons name="trash-outline" size={20} color={colors.red} /></TouchableOpacity></View>} ListEmptyComponent={<Empty text="Aún no tienes responsables registrados" />} />}<Modal visible={open} transparent animationType="slide"><View style={styles.modalWrap}><View style={styles.modal}><Text style={styles.modalTitle}>Nuevo responsable</Text><TextInput value={name} onChangeText={setName} placeholder="Nombre completo" style={styles.input} /><TextInput value={email} onChangeText={setEmail} placeholder="Correo electrónico" autoCapitalize="none" keyboardType="email-address" style={styles.input} /><TextInput value={relation} onChangeText={setRelation} placeholder="Parentesco (opcional)" style={styles.input} /><TouchableOpacity style={styles.primaryButton} onPress={create}><Text style={styles.primaryText}>Crear responsable</Text></TouchableOpacity><TouchableOpacity style={styles.cancelButton} onPress={() => setOpen(false)}><Text style={styles.cancelText}>Cancelar</Text></TouchableOpacity></View></View></Modal></>;
}

function Instructions() {
  const [items, setItems] = useState<Instruction[]>([]); const [accounts, setAccounts] = useState<Account[]>([]); const [beneficiaries, setBeneficiaries] = useState<Beneficiary[]>([]); const [open, setOpen] = useState(false); const [accountId, setAccountId] = useState(''); const [beneficiaryId, setBeneficiaryId] = useState(''); const [action, setAction] = useState<Instruction['accion']>('Conservar'); const [detail, setDetail] = useState(''); const [loading, setLoading] = useState(true);
  const load = async () => { setLoading(true); try { setItems((await api<Page<Instruction>>('/instructions')).items); } catch (e) { Alert.alert('Error', String(e)); } finally { setLoading(false); } };
  useEffect(() => { load(); api<Page<Account>>('/accounts').then((d) => setAccounts(d.items)); api<Page<Beneficiary>>('/beneficiaries').then((d) => setBeneficiaries(d.items)); }, []);
  const create = async () => { if (!accountId || (action === 'Transferir' && !beneficiaryId)) return Alert.alert('Completa los datos', 'Selecciona un activo y responsable si corresponde'); try { await api('/instructions', { method: 'POST', body: JSON.stringify({ id_activo: Number(accountId), id_beneficiario: beneficiaryId ? Number(beneficiaryId) : null, accion: action, detalle: detail || null }) }); setOpen(false); load(); } catch (e) { Alert.alert('Error', String(e)); } };
  return <><ScreenHeading title="Instrucciones" count={items.length} onAdd={() => setOpen(true)} />{loading ? <ActivityIndicator color={colors.green} /> : <FlatList data={items} keyExtractor={(item) => String(item.id_instruccion)} contentContainerStyle={styles.list} renderItem={({ item }) => <View style={styles.card}><View style={[styles.cardIcon, { backgroundColor: item.accion === 'Eliminar' ? '#F4E3E3' : colors.mint }]}><Ionicons name={item.accion === 'Transferir' ? 'swap-horizontal' : item.accion === 'Eliminar' ? 'trash-outline' : 'archive-outline'} size={20} color={item.accion === 'Eliminar' ? colors.red : colors.green} /></View><View style={styles.cardBody}><Text style={styles.cardTitle}>{item.nombre_activo}</Text><Text style={styles.cardMeta}>{item.accion}{item.beneficiario ? ` · ${item.beneficiario}` : ''}</Text>{item.detalle ? <Text style={styles.detail}>{item.detalle}</Text> : null}</View><TouchableOpacity onPress={() => Alert.alert('Eliminar instrucción', 'Esta acción no se puede deshacer', [{ text: 'Cancelar' }, { text: 'Eliminar', style: 'destructive', onPress: async () => { await api(`/instructions/${item.id_instruccion}`, { method: 'DELETE' }); load(); } }])}><Ionicons name="trash-outline" size={20} color={colors.red} /></TouchableOpacity></View>} ListEmptyComponent={<Empty text="Todavía no has definido instrucciones" />} />}<Modal visible={open} transparent animationType="slide"><View style={styles.modalWrap}><View style={styles.modal}><Text style={styles.modalTitle}>Nueva instrucción</Text><ScrollView><Text style={styles.label}>Activo</Text>{accounts.map((a) => <TouchableOpacity key={a.id_activo} style={[styles.choice, accountId === String(a.id_activo) && styles.choiceActive]} onPress={() => setAccountId(String(a.id_activo))}><Text style={accountId === String(a.id_activo) ? styles.choiceTextActive : styles.choiceText}>{a.nombre_activo}</Text></TouchableOpacity>)}<Text style={styles.label}>Acción</Text><View style={styles.segment}>{(['Eliminar','Transferir','Conservar'] as const).map((v) => <TouchableOpacity key={v} style={[styles.segmentItem, action === v && styles.segmentActive]} onPress={() => setAction(v)}><Text style={action === v ? styles.segmentTextActive : styles.segmentText}>{v}</Text></TouchableOpacity>)}</View>{action === 'Transferir' && <><Text style={styles.label}>Responsable</Text>{beneficiaries.map((b) => <TouchableOpacity key={b.id_beneficiario} style={[styles.choice, beneficiaryId === String(b.id_beneficiario) && styles.choiceActive]} onPress={() => setBeneficiaryId(String(b.id_beneficiario))}><Text style={beneficiaryId === String(b.id_beneficiario) ? styles.choiceTextActive : styles.choiceText}>{b.nombre_completo}</Text></TouchableOpacity>)}</>}<Text style={styles.label}>Detalle</Text><TextInput value={detail} onChangeText={setDetail} placeholder="Indicaciones opcionales" multiline style={[styles.input, { height: 84 }]} /><TouchableOpacity style={styles.primaryButton} onPress={create}><Text style={styles.primaryText}>Guardar instrucción</Text></TouchableOpacity><TouchableOpacity style={styles.cancelButton} onPress={() => setOpen(false)}><Text style={styles.cancelText}>Cancelar</Text></TouchableOpacity></ScrollView></View></View></Modal></>;
}

function Profile() {
  const [profile, setProfile] = useState<{ nombre_completo: string; email: string } | null>(null);
  useEffect(() => { api<{ nombre_completo: string; email: string }>('/users/me').then(setProfile).catch(() => {}); }, []);
  return <ScrollView contentContainerStyle={styles.profile}><Text style={styles.sectionTitle}>Mi perfil</Text><View style={styles.profileCard}><View style={styles.largeAvatar}><Text style={styles.largeAvatarText}>{profile?.nombre_completo?.charAt(0).toUpperCase() || 'A'}</Text></View><Text style={styles.profileName}>{profile?.nombre_completo || 'Usuario AfterKey'}</Text><Text style={styles.profileEmail}>{profile?.email || ''}</Text></View><View style={styles.infoRow}><Ionicons name="shield-checkmark-outline" size={22} color={colors.green} /><View style={{ flex: 1 }}><Text style={styles.infoTitle}>Tu legado está protegido</Text><Text style={styles.infoCopy}>Tus credenciales se cifran en el backend y solo tú puedes gestionarlas.</Text></View></View></ScrollView>;
}

function ScreenHeading({ title, count, onAdd }: { title: string; count: number; onAdd: () => void }) { return <View style={styles.headingRow}><View><Text style={styles.sectionTitle}>{title}</Text><Text style={styles.sectionCount}>{count} registros</Text></View><TouchableOpacity style={styles.addButton} onPress={onAdd}><Ionicons name="add" size={23} color={colors.white} /></TouchableOpacity></View>; }
function Empty({ text }: { text: string }) { return <View style={styles.empty}><Ionicons name="leaf-outline" size={38} color={colors.muted} /><Text style={styles.emptyText}>{text}</Text></View>; }

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.cream }, center: { flex: 1, justifyContent: 'center', alignItems: 'center' }, header: { height: 82, paddingHorizontal: 20, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderBottomWidth: 1, borderBottomColor: colors.line }, eyebrow: { fontSize: 11, fontWeight: '800', color: colors.green, letterSpacing: 1 }, title: { fontSize: 21, fontWeight: '700', color: colors.ink, marginTop: 3 }, iconButton: { width: 42, height: 42, borderRadius: 21, backgroundColor: colors.white, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.line }, content: { flex: 1 }, tabs: { height: 72, flexDirection: 'row', borderTopWidth: 1, borderTopColor: colors.line, backgroundColor: colors.white }, tabButton: { flex: 1, alignItems: 'center', justifyContent: 'center' }, tabLabel: { fontSize: 10, color: colors.muted, marginTop: 4, letterSpacing: 0 },
  authSafe: { flex: 1, backgroundColor: colors.cream, alignItems: 'center', justifyContent: 'center', padding: 24 }, brandMark: { width: 58, height: 58, borderRadius: 29, backgroundColor: colors.green, alignItems: 'center', justifyContent: 'center', marginBottom: 20 }, authTitle: { fontSize: 28, fontWeight: '800', color: colors.ink, textAlign: 'center' }, authCopy: { maxWidth: 320, fontSize: 15, lineHeight: 22, color: colors.muted, textAlign: 'center', marginTop: 8, marginBottom: 24 }, authForm: { width: '100%', maxWidth: 420 }, input: { height: 52, borderRadius: 8, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.white, paddingHorizontal: 14, marginBottom: 12, color: colors.ink }, error: { color: colors.red, marginBottom: 10, textAlign: 'center' }, primaryButton: { height: 52, borderRadius: 8, backgroundColor: colors.green, alignItems: 'center', justifyContent: 'center', marginTop: 4 }, primaryText: { color: colors.white, fontWeight: '700', fontSize: 15 }, linkText: { color: colors.green, fontWeight: '700', textAlign: 'center', marginTop: 18 },
  headingRow: { height: 76, paddingHorizontal: 20, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }, sectionTitle: { fontSize: 22, fontWeight: '800', color: colors.ink }, sectionCount: { fontSize: 13, color: colors.muted, marginTop: 3 }, addButton: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.green, alignItems: 'center', justifyContent: 'center' }, list: { paddingHorizontal: 16, paddingBottom: 20 }, card: { minHeight: 82, backgroundColor: colors.white, borderRadius: 8, borderWidth: 1, borderColor: colors.line, marginBottom: 10, padding: 12, flexDirection: 'row', alignItems: 'center' }, cardIcon: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.mint, alignItems: 'center', justifyContent: 'center', marginRight: 12 }, cardBody: { flex: 1 }, cardTitle: { fontSize: 16, fontWeight: '700', color: colors.ink }, cardMeta: { fontSize: 13, color: colors.muted, marginTop: 4 }, detail: { fontSize: 12, color: colors.ink, marginTop: 5 }, avatar: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.ink, alignItems: 'center', justifyContent: 'center', marginRight: 12 }, avatarText: { color: colors.white, fontSize: 18, fontWeight: '800' }, empty: { alignItems: 'center', marginTop: 100, paddingHorizontal: 40 }, emptyText: { color: colors.muted, textAlign: 'center', marginTop: 10 },
  modalWrap: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(23,34,27,0.35)' }, modal: { maxHeight: '86%', backgroundColor: colors.cream, borderTopLeftRadius: 16, borderTopRightRadius: 16, padding: 20 }, modalTitle: { fontSize: 21, fontWeight: '800', color: colors.ink, marginBottom: 18 }, label: { fontSize: 13, fontWeight: '700', color: colors.ink, marginBottom: 8, marginTop: 4 }, choice: { height: 46, borderWidth: 1, borderColor: colors.line, borderRadius: 8, backgroundColor: colors.white, justifyContent: 'center', paddingHorizontal: 12, marginBottom: 7 }, choiceActive: { borderColor: colors.green, backgroundColor: colors.mint }, choiceText: { color: colors.ink }, choiceTextActive: { color: colors.green, fontWeight: '700' }, segment: { height: 44, flexDirection: 'row', marginBottom: 12, borderRadius: 8, borderWidth: 1, borderColor: colors.line, overflow: 'hidden' }, segmentItem: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.white }, segmentActive: { backgroundColor: colors.green }, segmentText: { color: colors.muted, fontSize: 12 }, segmentTextActive: { color: colors.white, fontWeight: '700', fontSize: 12 }, cancelButton: { height: 44, alignItems: 'center', justifyContent: 'center', marginTop: 8 }, cancelText: { color: colors.muted, fontWeight: '700' },
  profile: { padding: 20 }, profileCard: { backgroundColor: colors.white, borderWidth: 1, borderColor: colors.line, borderRadius: 8, alignItems: 'center', paddingVertical: 28, marginTop: 16 }, largeAvatar: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.ink, alignItems: 'center', justifyContent: 'center' }, largeAvatarText: { color: colors.white, fontSize: 28, fontWeight: '800' }, profileName: { fontSize: 18, fontWeight: '800', color: colors.ink, marginTop: 12 }, profileEmail: { color: colors.muted, marginTop: 4 }, infoRow: { flexDirection: 'row', gap: 12, backgroundColor: colors.mint, borderRadius: 8, padding: 16, marginTop: 12 }, infoTitle: { fontWeight: '700', color: colors.ink }, infoCopy: { color: colors.muted, lineHeight: 19, marginTop: 4 },
});
