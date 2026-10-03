import fcntl
import json
import os
import tempfile
from pathlib import Path


# Reviews live in one json file keyed by case id. Every write goes through a
# temp file + os.replace so a half written file can never be read back, and
# flock because flask may serve two of these at once.
class ReviewStore:
    def __init__(self, path):
        self.path = Path( path )

    def get( self,case_id):


        if not self.path.exists ( ):
            return None
        with self.path.open(encoding="utf-8") as file :
            return json.load(file).get(str(case_id))


    def add(self , case_id , review ):
        return self._write (case_id , review,replace= False)

    def update( self, case_id ,review):
        return self._write(case_id, review, replace=True)

    #duplicated from _write on purpose, wanted the status branch kept separate
    def update_status(self,case_id,status) :


        self.path.parent.mkdir( parents=True,exist_ok=True )
        with (self.path.parent / (self.path.name + ".lock")).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data ={}
            if self.path.exists():
                with self.path.open(encoding="utf-8") as file:

                    data = json.load(file)
            key = str(case_id)
            if key not in data:
                return False
            data[key]["status"] = status
            temporary = None
            try :
                with tempfile.NamedTemporaryFile (
                    mode ="w", encoding="utf-8" ,dir = self.path.parent ,delete=False
                )as file:

                    temporary = file.name
                    json.dump(data, file, ensure_ascii=False, indent=2)
                    file.flush()
                    os.fsync( file.fileno() ) # crash safe, the parent dir rename is what matters
                os.replace(temporary, self.path)
            finally :
                if temporary and os.path.exists(temporary):
                    os.unlink ( temporary )
            return True

    #returns False when the state machine says no, caller turns that into a 409
    def _write( self, case_id, review,replace ) :
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with ( self.path.parent/ ( self.path.name +".lock")).open ("a")as lock :
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = {}
            if self.path.exists ( ):
                with self.path.open( encoding= "utf-8") as file :
                    data = json.load(file)
            key=str ( case_id )
            if replace :
                #only swapable while the survey is still outstanding
                if key not in data or data[key].get("status") != "awaiting_survey":
                    return False
            elif key in data :

                return False
            data[key]= review
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",encoding="utf-8",dir = self.path.parent,delete = False
                )as file:
                    temporary = file.name
                    json.dump( data, file,ensure_ascii =False,indent= 2 )
                    file.flush()
                    os.fsync (file.fileno ( ) )
                os.replace (temporary, self.path )
            finally:
                if temporary and os.path.exists(temporary) :
                    os.unlink(temporary)
            return True
