"use client";
import {createContext,useContext,useEffect,useState,ReactNode} from 'react';
import {api} from '@/lib/api';
const defaults={name:'Engram',tagline:'private cognition layer',accent:'#b6ff4a',logo:''};
const Context=createContext(defaults);
export const useBranding=()=>useContext(Context);
export function BrandingProvider({children}:{children:ReactNode}){
 const [brand,setBrand]=useState(defaults);
 useEffect(()=>{api<typeof defaults>('/api/v1/branding').then(value=>{setBrand(value);document.documentElement.style.setProperty('--accent',value.accent);document.title=value.name}).catch(()=>{})},[]);
 return <Context.Provider value={brand}>{children}</Context.Provider>;
}
