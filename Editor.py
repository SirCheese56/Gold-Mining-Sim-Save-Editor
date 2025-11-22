import os,zipfile,tkinter as tk
from tkinter import ttk,messagebox,filedialog
import xml.etree.ElementTree as ET,shutil

ZIP_PASSWORD="HiChat!"
DEFAULT_SAVE_PATH=os.path.join(os.path.normpath(os.path.join(os.getenv("APPDATA",""),"..","LocalLow")),"CodeHorizon","GoldMiningSimulator","Saves","AutoSave","CheckpointData.sav")
PINNED_KEYS=["Cash","Gold","Diamonds","Magnetide","GordNugets","SumOfMeltedGold","Difficulty"]

def load_xml_from_save(path):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Save not found: {path}")
    with zipfile.ZipFile(path,"r") as z:
        infos=z.infolist()
        if not infos:
            raise RuntimeError("No entries found in save ZIP.")
        info=infos[0]
        with z.open(info,pwd=ZIP_PASSWORD.encode("utf-8")) as f:
            xml_bytes=f.read()
    root=ET.fromstring(xml_bytes.decode("utf-8",errors="ignore"))
    return ET.ElementTree(root),root,info.filename

def find_gamestate_manager(root):
    gm_obj=None
    for go in root.findall(".//GameObject"):
        if go.attrib.get("Name")=="GameManager":
            gm_obj=go
            break
    if gm_obj is None:
        raise RuntimeError("GameManager GameObject not found in XML.")
    gsm=None
    for comp in gm_obj.findall(".//Component"):
        if comp.attrib.get("Name")=="GoldDigger.GameStateManager":
            gsm=comp
            break
    if gsm is None:
        raise RuntimeError("GoldDigger.GameStateManager component not found.")
    keys_container=gsm.find("Keys")
    if keys_container is None:
        raise RuntimeError("Keys node not found in GameStateManager.")
    return keys_container

def extract_keys(keys_container):
    result={}
    for key_elem in keys_container.findall("Key"):
        kname=key_elem.attrib.get("Key")
        val_elem=None
        vtype=None
        for child in key_elem:
            if child.tag in("StringValue","FloatValue","IntValue","BoolValue"):
                val_elem=child
                vtype=child.tag
                break
        if not kname or val_elem is None:
            continue
        result[kname]={"elem":key_elem,"type":vtype,"val_elem":val_elem}
    return result

def write_xml_to_save(tree,entry_name,save_path,backup=True):
    xml_bytes=ET.tostring(tree.getroot(),encoding="utf-8",xml_declaration=True)
    if backup and os.path.exists(save_path):
        backup_path=save_path+".bak"
        shutil.copy2(save_path,backup_path)
    tmp_path=save_path+".tmp"
    with zipfile.ZipFile(tmp_path,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(entry_name,xml_bytes)
    os.replace(tmp_path,save_path)

class SaveEditorApp:
    def __init__(self,master):
        self.master=master
        master.title("Gold Mining Simulator Save Editor")
        self.save_path=DEFAULT_SAVE_PATH
        self.tree=None
        self.root_xml=None
        self.entry_name=None
        self.keys_dict={}
        self.current_key_name=None
        self.all_keys=[]
        self.filtered_keys=[]
        self.build_ui()
        self.master.after(50,self.load_save_initial)

    def build_ui(self):
        top_frame=ttk.Frame(self.master,padding=5)
        top_frame.pack(fill="x")
        ttk.Label(top_frame,text="Save path:").pack(side="left")
        self.path_var=tk.StringVar(value=self.save_path)
        path_entry=ttk.Entry(top_frame,textvariable=self.path_var,width=90)
        path_entry.pack(side="left",padx=5,expand=True,fill="x")
        ttk.Button(top_frame,text="Browse...",command=self.browse_save).pack(side="left",padx=3)
        ttk.Button(top_frame,text="Reload",command=self.load_save_interactive).pack(side="left",padx=3)

        search_frame=ttk.Frame(self.master,padding=(5,0,5,5))
        search_frame.pack(fill="x")
        ttk.Label(search_frame,text="Search keys:").pack(side="left")
        self.search_var=tk.StringVar()
        search_entry=ttk.Entry(search_frame,textvariable=self.search_var,width=30)
        search_entry.pack(side="left",padx=5)
        search_entry.bind("<KeyRelease>",self.on_search_changed)

        pinned_frame=ttk.LabelFrame(self.master,text="Important values",padding=5)
        pinned_frame.pack(fill="x",padx=5,pady=5)
        self.pinned_entries={}
        row=0
        for k in PINNED_KEYS:
            lbl=ttk.Label(pinned_frame,text=k+":")
            lbl.grid(row=row,column=0,sticky="e",padx=3,pady=2)
            ent=ttk.Entry(pinned_frame,width=20)
            ent.grid(row=row,column=1,sticky="w",padx=3,pady=2)
            type_lbl=ttk.Label(pinned_frame,text="",width=12)
            type_lbl.grid(row=row,column=2,sticky="w",padx=3,pady=2)
            self.pinned_entries[k]=(ent,type_lbl)
            row+=1
        ttk.Button(pinned_frame,text="Apply pinned changes",command=self.apply_pinned_changes).grid(row=row,column=0,columnspan=3,pady=5)

        mid_frame=ttk.Frame(self.master,padding=5)
        mid_frame.pack(fill="both",expand=True)

        left_frame=ttk.Frame(mid_frame)
        left_frame.pack(side="left",fill="both",expand=False)
        ttk.Label(left_frame,text="All GameStateManager keys:").pack(anchor="w")

        self.listbox=tk.Listbox(left_frame,height=25,exportselection=False)
        self.listbox.pack(side="left",fill="both",expand=True)
        self.listbox.bind("<<ListboxSelect>>",self.on_select_key)
        scroll=ttk.Scrollbar(left_frame,orient="vertical",command=self.listbox.yview)
        scroll.pack(side="right",fill="y")
        self.listbox.config(yscrollcommand=scroll.set)

        right_frame=ttk.LabelFrame(mid_frame,text="Selected key editor",padding=5)
        right_frame.pack(side="left",fill="both",expand=True,padx=5)

        self.sel_name_var=tk.StringVar()
        self.sel_type_var=tk.StringVar()
        self.sel_value_var=tk.StringVar()

        ttk.Label(right_frame,text="Key:").grid(row=0,column=0,sticky="e",padx=3,pady=3)
        ttk.Entry(right_frame,textvariable=self.sel_name_var,state="readonly",width=30).grid(row=0,column=1,sticky="w",padx=3,pady=3)
        ttk.Label(right_frame,text="Type:").grid(row=1,column=0,sticky="e",padx=3,pady=3)
        ttk.Entry(right_frame,textvariable=self.sel_type_var,state="readonly",width=15).grid(row=1,column=1,sticky="w",padx=3,pady=3)
        ttk.Label(right_frame,text="Value:").grid(row=2,column=0,sticky="e",padx=3,pady=3)
        self.value_entry=ttk.Entry(right_frame,textvariable=self.sel_value_var,width=40)
        self.value_entry.grid(row=2,column=1,sticky="w",padx=3,pady=3)
        ttk.Button(right_frame,text="Apply change",command=self.apply_selected_change).grid(row=3,column=0,columnspan=2,pady=5)

        bottom_frame=ttk.Frame(self.master,padding=5)
        bottom_frame.pack(fill="x")
        ttk.Button(bottom_frame,text="Save changes to file",command=self.save_to_disk).pack(side="left",padx=5)
        ttk.Button(bottom_frame,text="Quit",command=self.master.quit).pack(side="right",padx=5)

    def load_save_initial(self):
        self.load_save_interactive(initial=True)

    def browse_save(self):
        path=filedialog.askopenfilename(title="Select CheckpointData.sav",filetypes=[("Gold Mining Sim save","*.sav"),("All files","*.*")])
        if path:
            self.save_path=path
            self.path_var.set(path)
            self.load_save_interactive()

    def load_save_interactive(self,initial=False):
        path=self.path_var.get().strip()
        if not path:
            path=DEFAULT_SAVE_PATH
            self.path_var.set(path)
        try:
            tree,root,entry_name=load_xml_from_save(path)
            keys_container=find_gamestate_manager(root)
            keys_dict=extract_keys(keys_container)
        except Exception as e:
            if not initial:
                messagebox.showerror("Error",f"Failed to load save.\n\n{e}")
            return
        self.save_path=path
        self.tree=tree
        self.root_xml=root
        self.entry_name=entry_name
        self.keys_dict=keys_dict
        self.all_keys=sorted(self.keys_dict.keys(),key=str.lower)
        self.refresh_key_list()
        self.update_pinned_fields()
        if self.filtered_keys:
            self.listbox.select_set(0)
            self.on_select_key(None)

    def refresh_key_list(self):
        search=self.search_var.get().strip().lower()
        self.listbox.delete(0,tk.END)
        if search:
            self.filtered_keys=[k for k in self.all_keys if search in k.lower()]
        else:
            self.filtered_keys=list(self.all_keys)
        for k in self.filtered_keys:
            self.listbox.insert(tk.END,k)

    def update_pinned_fields(self):
        for k,(entry,type_lbl) in self.pinned_entries.items():
            info=self.keys_dict.get(k)
            if info:
                val_elem=info["val_elem"]
                entry.delete(0,tk.END)
                entry.insert(0,val_elem.text if val_elem.text is not None else "")
                type_lbl.config(text=info["type"])
            else:
                entry.delete(0,tk.END)
                type_lbl.config(text="(missing)")

    def on_search_changed(self,event=None):
        self.refresh_key_list()

    def on_select_key(self,event):
        sel=self.listbox.curselection()
        if not sel:
            return
        idx=sel[0]
        if idx<0 or idx>=len(self.filtered_keys):
            return
        key_name=self.filtered_keys[idx]
        info=self.keys_dict.get(key_name)
        if not info:
            return
        self.current_key_name=key_name
        self.sel_name_var.set(key_name)
        self.sel_type_var.set(info["type"])
        self.sel_value_var.set(info["val_elem"].text if info["val_elem"].text is not None else "")
        self.value_entry.focus_set()

    def apply_selected_change(self):
        if not self.current_key_name:
            messagebox.showwarning("No key","No key selected.")
            return
        info=self.keys_dict.get(self.current_key_name)
        if not info:
            messagebox.showerror("Error","Selected key not found in internal map.")
            return
        new_val=self.sel_value_var.get()
        info["val_elem"].text=new_val
        if self.current_key_name in self.pinned_entries:
            entry,_=self.pinned_entries[self.current_key_name]
            entry.delete(0,tk.END)
            entry.insert(0,new_val)

    def apply_pinned_changes(self):
        if not self.keys_dict:
            messagebox.showwarning("No data","No save is loaded.")
            return
        for k,(entry,_) in self.pinned_entries.items():
            info=self.keys_dict.get(k)
            if not info:
                continue
            new_val=entry.get()
            info["val_elem"].text=new_val

    def save_to_disk(self):
        if not self.tree or not self.save_path:
            messagebox.showwarning("No data","No save loaded.")
            return
        try:
            write_xml_to_save(self.tree,self.entry_name,self.save_path,backup=True)
        except Exception as e:
            messagebox.showerror("Error",f"Failed to save.\n\n{e}")
            return
        messagebox.showinfo("Saved",f"Changes saved.\nBackup created as:\n{self.save_path}.bak")

if __name__=="__main__":
    root=tk.Tk()
    app=SaveEditorApp(root)
    root.mainloop()
